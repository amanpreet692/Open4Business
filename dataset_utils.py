import csv
import logging
import os
import re

from parse_doc2xml import  SENTENCE_BOUNDARY
from time import sleep

import lxml.etree as parser
import requests
from lxml.etree import XPath
from unpywall import Unpywall

logger = logging.getLogger(__name__)
namespaces = {'x': 'http://www.tei-c.org/ns/1.0', }
ABSTRACT_XPATH_QUERY = XPath(".//x:abstract/x:div/x:p", namespaces=namespaces)
TITLE_XPATH_QUERY = XPath(".//x:titleStmt/x:title", namespaces=namespaces)
BODY_XPATH_QUERY = XPath(".//x:body/x:div", namespaces=namespaces)
TEXT_CONTENT_XPATH_QUERY = XPath("string()")
CTR = 0
STRIP_TAGS_LIST = ["ref"]
STRIP_ELEMENTS_LIST = ["head", "formula"]


def init_logger(logging_level):
    handler = logging.StreamHandler()
    handler.setLevel(logging_level)
    handler.setFormatter(logging.Formatter('[%(asctime)s] - [%(process)d] - [%(levelname)s] - %(message)s'))
    logger = logging.getLogger(__name__)
    logger.setLevel(logging_level)
    logger.addHandler(handler)
    return logger


def download_pdf_file(url: str,
                      filename: str,
                      filepath: str = '.',
                      progress: bool = False) -> None:
    """
    This function downloads a PDF from a given DOI.

    @:param
    ----------
    url : url
        Download url for the article.
    filename : str
        The filename for the PDF.
    filepath : str
        The path to store the downloaded PDF.
    progress : bool
        Whether the progress of the API call should be printed out or not.
    """
    try:
        headers = {
            "User-Agent": "python"
        }
        r = requests.get(url, stream=url, headers=headers)
        if r.status_code == 200:
            file_size = int(r.headers.get('content-length', 0))
            block_size = 1024

            path = os.path.join(filepath, filename)

            if not os.path.exists(filepath):
                os.makedirs(filepath)

            with open(path, 'wb') as file:
                chunk_size = 0
                for chunk in r.iter_content(block_size):
                    if progress and file_size > 0:
                        chunk_size += len(chunk)
                        Unpywall._progress(chunk_size / file_size)
                    file.write(chunk)
        else:
            logger.warning("Not able to download file, Http Response: {}".format(r.status_code))
    except ConnectionError:
        logger.warning('Connection error received, will retry after 10 secs')
        sleep(10)
        Unpywall.download_pdf_file(url, filename, filepath)
    except Exception:
        logger.warning('Rethrowing error')
        raise


def pre_process(text):
    text = text.replace(".", "")
    text = text.replace('"', "")
    return text.strip()


def get_journals_from_csv(path):
    journal_dict = {}
    logger.info("Priming the journal info from file: {}".format(path))
    with open(path) as csvfile:
        read_csv = csv.reader(csvfile, delimiter=',')
        for row in read_csv:
            # if detect(row[2]) == 'en':
            journal_dict[row[0]] = pre_process(row[2])
            # else:
            #     print(row[2])
    return journal_dict


def post_process(node_text):
    node_text = str(node_text).strip()
    node_text = re.sub("\[\d+\]", "", node_text)
    node_text = re.sub("\(\d{4}\)", "", node_text)
    node_text = node_text.replace("&", " and ")
    node_text = node_text.replace("et al.", "")
    node_text = re.sub("\s{2,}", " ", node_text)
    return node_text


def filter_data(text):
    spanish_words = [' la ', ' de ', ' los ']
    # French
    if text.count(" les ") > 5:
        return False
    # Russian
    if "да" in text.lower():
        return False
    # Spanish
    spanish_count = 0
    for word in spanish_words:
        if text.count(word) > 5:
            spanish_count += 1
    if spanish_count == len(spanish_words):
        return False
    if ' je ' in text:
        return False
    return True


def get_data_from_xml(path=None, xml_text=None, **xpath_kwargs):
    result_dict = {}
    if path is not None:
        logger.debug('Parsing the xml file @ {} for summary and content...'.format(path))
        root = parser.parse(open(path, encoding="utf8"))
    elif xml_text is not None:
        root = parser.fromstring(xml_text)

    title_xpath_query = xpath_kwargs.pop('title_query', TITLE_XPATH_QUERY)
    abstract_xpath_query = xpath_kwargs.pop('abstract_query', ABSTRACT_XPATH_QUERY)
    body_xpath_query = xpath_kwargs.pop('body_query', BODY_XPATH_QUERY)
    strip_tags_list = xpath_kwargs.pop('strip_tags_list', STRIP_TAGS_LIST)
    strip_elements_list = xpath_kwargs.pop('strip_elemnts_list', STRIP_ELEMENTS_LIST)
    namespace = xpath_kwargs.pop('namespaces', namespaces["x"])

    title_node = title_xpath_query(root)
    abstract_node = abstract_xpath_query(root)

    if len(abstract_node) == 0:
        return None
    parser.strip_elements(abstract_node[0], strip_elements_list)

    title_text = title_node[0].text
    abstract_text = TEXT_CONTENT_XPATH_QUERY(abstract_node[0])
    abstract_text = str(abstract_text).strip().replace("\n", " ")
    if title_text is not None:
        result_dict['summary'] = title_text.strip() + '. ' + abstract_text
    else:
        result_dict['summary'] = abstract_text

    body_nodes = body_xpath_query(root)
    body_text = []
    for node in body_nodes:
        parser.strip_tags(node, list(map(lambda x: append_namespace_to_tag(x, namespace), strip_tags_list)))
        parser.strip_elements(node,
                              list(map(lambda x: append_namespace_to_tag(x, namespace), strip_elements_list)))
        node_text = TEXT_CONTENT_XPATH_QUERY(node)
        post_processed_text = post_process(node_text)
        if len(post_processed_text) > 0:
            body_text.append(post_processed_text)
    result_dict['content'] = ' '.join(body_text)
    if result_dict['content'] == '' or not filter_data(result_dict['content']) or not filter_data(
            result_dict['summary']):
        return None
    result_dict['content'] = result_dict['content'][0].upper()+result_dict['content'][1:]
    result_dict['summary'] = result_dict['summary'][0].upper() + result_dict['summary'][1:]
    if result_dict['content'][-1] not in SENTENCE_BOUNDARY:
        result_dict['content'] = result_dict['content']+'.'
    if result_dict['summary'][-1] not in SENTENCE_BOUNDARY:
        result_dict['summary'] = result_dict['summary']+'.'
    return result_dict


def append_namespace_to_tag(tag, namespace=None):
    return '{{{}}}{}'.format(namespace, tag) if namespace is not None else tag


def download_frm_scirp(doc_list):
    title_query = XPath('.//article-title')
    abstract_query = XPath('.//abstract/p')
    body_query = XPath('.//body/sec')
    strip_elements_list = ['xref', 'title', 'b', 'sup', 'table-wrap']
    logger.info("Will retry processing for {} scirp faulty files".format(len(doc_list)))
    result_dict_list = []
    for file_name, doc_id in doc_list:
        logger.debug('Processing : {}'.format(file_name))
        urlfile = "https://www.scirp.org/xml/{}.xml".format(str(doc_id))
        try:
            response = requests.get(urlfile)
            if response.status_code == 200:
                xml_text = response.content
                xml_text = re.sub('<sup>|</sup>|<b>|</b>', '', xml_text.decode('utf-8')).encode('utf-8')
                result_dict = get_data_from_xml(xml_text=xml_text, title_query=title_query,
                                                abstract_query=abstract_query,
                                                body_query=body_query, strip_elemnts_list=strip_elements_list,
                                                strip_tags_list=[], namespaces=None)
                result_dict_list.append(result_dict)
                with open(file_name, 'wb') as file:
                    file.write(xml_text)
        except Exception as e:
            logger.info("No substitute XML exists for {}".format(file_name))
    return result_dict_list


diff_src_fn_dict = {"scirp": download_frm_scirp}


def download_frm_another_src(diff_src_dict):
    result_dict_list = []
    for src in diff_src_dict:
        result_dict = diff_src_fn_dict[src](diff_src_dict[src])
        result_dict_list.extend(result_dict)
    return result_dict_list
