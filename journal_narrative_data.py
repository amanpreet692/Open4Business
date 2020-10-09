import glob
import argparse
import logging
import ntpath
import pickle
from os import path, remove
from time import sleep

from crossref.restful import Journals, Works
from requests.exceptions import HTTPError
from tqdm import tqdm
from unpywall import Unpywall, UnpywallCache
from unpywall.utils import UnpywallCredentials

from dataset_generation.dataset_utils import download_pdf_file, init_logger, get_journals_from_csv, get_data_from_xml, \
    download_frm_another_src

DATA_DIR = './data_prime'

DOI_CACHE_PATH = path.join(DATA_DIR, "dois.pkl")
URL_CACHE_PATH = path.join(DATA_DIR, "urls.pkl")

logger = logging.getLogger(__name__)


class NarrativeDataset:
    LICENSE_WHITELIST = ['http://creativecommons.org/licenses/by/4.0/', 'http://creativecommons.org/licenses/by/3.0/']
    download_links = dict()

    def __init__(self, reset_cache=False):
        self.journals = Journals()
        self.works = Works()
        self.filter_kwargs = dict(
            has_license='true',
            has_full_text='true')
        self.keywords = 'business financial merger entrepreneur banking insurance commerce trade economics'
        UnpywallCredentials('abc123@gmail.com')
        cache_path = path.join(DATA_DIR, 'unpaywall_cache')
        if reset_cache and path.exists(cache_path):
            remove(cache_path)
        self.unpywall_cache = UnpywallCache(cache_path)
        Unpywall.init_cache(self.unpywall_cache)

    def get_dois_from_journal(self, journal_issn):
        doi_list = []
        try:
            if self.journals.journal_exists(journal_issn):
                works = self.journals.works(journal_issn).filter(**self.filter_kwargs).select('DOI', 'license')
                for response_dict in tqdm(works):
                    license_dict = response_dict['license']
                    if self.is_license_whitelist(license_dict[0]['URL']):
                        doi_list.append(response_dict['DOI'])
        except Exception as e:
            logger.error("Error while getting DOIs from REST service", e, exc_info=True)
        return doi_list

    def get_dois_from_keywords(self):
        doi_list = []
        try:
            results = self.works.query(self.keywords).filter(**self.filter_kwargs).select('DOI', 'license')
            for response_dict in tqdm(results):
                license_dict = response_dict['license']
                if self.is_license_whitelist(license_dict[0]['URL']):
                    doi_list.append(response_dict['DOI'])
        except Exception as e:
            logger.error("Error while getting DOIs from REST service", e, exc_info=True)
        return doi_list

    def get_oa_urls(self, doi_list):
        logger.info('Retreiving doc urls for DOIs now (cached/uncached)')
        oa_urls = []
        for i, doi in tqdm(enumerate(doi_list), total=len(doi_list)):
            try:
                oa_urls.append(Unpywall.get_doc_link(doi))
            except HTTPError:
                logger.warning('\nError received for DOI: {}, will retry 3 times in 20 secs'.format(doi))
                sleep(20)
                for i in range(3):
                    try:
                        logger.info('Retry :{}'.format(i + 1))
                        oa_urls.append(Unpywall.get_doc_link(doi))
                        break
                    except HTTPError as e:
                        logger.error('Retry failed', e, exc_info=True)
        return oa_urls

    def is_license_whitelist(self, license):
        license = str(license).replace('https', 'http')
        return license in self.LICENSE_WHITELIST

    def retry_from_another_src(self, faulty_files_list, doi_list):
        src_dict = {'scirp': []}
        for file in faulty_files_list:
            base_name = ntpath.basename(file)
            doi_list_ind = int(base_name.replace("Sample_", "")[:-8]) - 1
            doi = doi_list[doi_list_ind]
            doc_url = Unpywall.get_pdf_link(doi)
            if doc_url is not None and 'scirp' in doc_url.lower():
                try:
                    scirp_id = doc_url[doc_url.index('paperID=') + 8:]
                except (IndexError, ValueError):
                    continue
                if scirp_id != "":
                    src_dict['scirp'].append((file, scirp_id))
        return download_frm_another_src(src_dict)

    @staticmethod
    def download_doi_pdf(works, doi_list, download_dir):
        logger.info("Trying to download the required data now for {} DOIs".format(len(doi_list)))
        for i, doi in enumerate(doi_list):

                name_pattern = 'Sample_{}.pdf'.format(str(i + 1))
                download_link = Unpywall.get_pdf_link(doi)
                try:
                    if not download_link:
                        result = works.doi(doi)['link']
                        for item in result:
                            application = item['intended-application']
                            type = item['content-type']
                            if application is not None and application == 'text-mining' and type == 'application/pdf':
                                download_link = item['URL']
                                break
                    NarrativeDataset.download_links[name_pattern[:-4]] = download_link
                    if not path.exists(path.join(download_dir, name_pattern)):
                        if download_link and filter_url(download_link):
                            logger.debug('Downloading ' + name_pattern + " : " + doi + ' from url: ' + download_link)
                            download_pdf_file(download_link, name_pattern, download_dir, progress=True)
                            sleep(5)
                except Exception as e:
                    logger.error("Error while downloading the article ({}, {})".format(str(i + 1), doi), e, exc_info=True)
                    NarrativeDataset.download_links[name_pattern[:-4]] = download_link
        return True


def filter_url(doi_url):
    filter_url_list = ['biomedcentral', 'journals.plos', 'peerj.com', 'pubs.rsc.org', 'aps.org']
    for url in filter_url_list:
        if url in doi_url:
            return False
    return True


def download_doi_from_api(narr_dataset):
    complete_doi_list = []
    journals = get_journals_from_csv(path.join(DATA_DIR, 'oa_gold_access.csv'))
    pbar = tqdm(journals)
    for journal_issn in pbar:
        pbar.set_description('Processing: {}'.format(journals[journal_issn]))
        complete_doi_list.extend(narr_dataset.get_dois_from_journal(journal_issn))
    complete_doi_set = set(complete_doi_list)
    sleep(30)
    print(len(complete_doi_list))
    logger.info("Obtaining DOI based on keywords")
    keywords_doi_list = narr_dataset.get_dois_from_keywords()
    for doi in keywords_doi_list:
        if doi not in complete_doi_set:
            complete_doi_list.append(doi)
            complete_doi_set.add(doi)

    doi_list = []
    if len(complete_doi_list) > 0:
        doi_list = list(complete_doi_list)
        pickle.dump(doi_list, open(DOI_CACHE_PATH, "wb"))
    return doi_list


def get_downld_urls_from_api(complete_doi_list, narr_dataset):
    url_list = narr_dataset.get_oa_urls(complete_doi_list)
    if len(url_list) > 0:
        pickle.dump(url_list, open(URL_CACHE_PATH, "wb"))
    return url_list


def parse_gen_xml(narr_dataset, complete_doi_list, converted_files_list):
    dataset_src = []
    dataset_target = []
    faulty_files = []

    converted_files_dir = path.dirname(converted_files_list[0])
    for i in range(1, len(complete_doi_list) + 1):
        name_pattern = 'Sample_{}'.format(str(i))
        if path.join(converted_files_dir, name_pattern + '.tei.xml') not in converted_files_list:
            NarrativeDataset.download_links.pop(name_pattern)
    ctr = 1
    for i, file in tqdm(enumerate(converted_files_list), total=len(converted_files_list)):
        result_dict = get_data_from_xml(file)
        if result_dict is not None:
            dataset_src.append(result_dict['content'])
            dataset_target.append(result_dict['summary'])
            ctr += 1
        else:
            faulty_files.append(file)
    for i, result_dict in enumerate(narr_dataset.retry_from_another_src(faulty_files.copy(), complete_doi_list)):
        if result_dict is not None:
            faulty_files.pop(i)
            dataset_src.append(result_dict['content'])
            dataset_target.append(result_dict['summary'])

    for faulty_file in faulty_files:
        key = path.basename(faulty_file)[:-8]
        NarrativeDataset.download_links.pop(key)

    return dataset_src, dataset_target


def add_parser_args(parser):
    parser.add_argument("--force", action="store_true", default=False, help="Force redownload urls")
    parser.add_argument("--download", action="store_true", default=False, help="Download the pdf files")
    parser.add_argument("--parse", action="store_true", default=False, help="Parse the converted xml files")
    parser.add_argument("--reset_cache", action="store_true", default=False, help="Delete cached data")
    parser.add_argument("--xml_path", default="./converted_articles", help="Path where converted xmls are stored")
    pass


if __name__ == "__main__":
    logger = init_logger(logging.DEBUG)
    parser = argparse.ArgumentParser()
    add_parser_args(parser)
    args = parser.parse_args()

    narr_dataset = NarrativeDataset(args.reset_cache)
    complete_doi_list = []
    url_list = []
    try:
        if args.force:
            logger.info("Downloading the DOI and License info from CrossRef Api")
            complete_doi_list = download_doi_from_api(narr_dataset)
            # complete_doi_list = list(pickle.load(open(DOI_CACHE_PATH, "rb")))
        else:
            complete_doi_list = list(pickle.load(open(DOI_CACHE_PATH, "rb")))
            logger.info("Loaded DOI info from {}".format(DOI_CACHE_PATH))
    except (FileNotFoundError, IOError) as e:
        logger.warning("Cached copy of DOIs doesn't exist, will call CrossRef REST API")
        complete_doi_list = download_doi_from_api(narr_dataset)
    try:
        if args.force:
            logger.info("Downloading the URL infor for Dois from Unpywall from scratch")
            url_list = get_downld_urls_from_api(complete_doi_list, narr_dataset)
        else:
            url_list = pickle.load(open(URL_CACHE_PATH, "rb"))
            logger.info("Loaded Open Access URLs from cache: {}".format(URL_CACHE_PATH))
    except (FileNotFoundError, IOError) as e:
        logger.warning("Cached copy of URLs doesn't exist, will Call Unpaywall REST API")
        url_list = get_downld_urls_from_api(complete_doi_list, narr_dataset)

    if args.download and len(url_list) > 0:
        if NarrativeDataset.download_doi_pdf(narr_dataset.works, doi_list=complete_doi_list, download_dir='./download_articles'):
            logger.info("Finished Downloading the articles, commencing further processing...")
    else:
        logger.info("Nothing to download, loading files from cache for further processing...")

    if args.parse:
        converted_files_list = glob.glob(path.join(args.xml_path, 'S*.tei.xml'))

        dataset_src, dataset_target = parse_gen_xml(narr_dataset, complete_doi_list, converted_files_list)
        pickle.dump(NarrativeDataset.download_links, open(path.join(DATA_DIR, 'download_links.pkl'), "wb"))

        pickle.dump(dataset_src, open(path.join(DATA_DIR, 'source.pkl'), "wb"))
        pickle.dump(dataset_target, open(path.join(DATA_DIR, 'target.pkl'), "wb"))

        logger.info('Was able to process {} out of {} files'.format(len(dataset_src), len(converted_files_list)))
