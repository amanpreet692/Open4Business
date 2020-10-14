import re
import sys
import json
import pickle
import random
import numpy as np
from tqdm import tqdm
from pathlib import Path
from nltk import tokenize
from unidecode import unidecode
from abc import ABC, abstractmethod
from sklearn.model_selection import train_test_split

USC_re = re.compile('[Uu]\.*[Ss]\.*[Cc]\.]+')
PAREN_re = re.compile('\([^(]+[^(]+\)')
BAD_PUNCT_RE = re.compile(r'([%s])' % re.escape('"#%&\*\+/<=>@[\]^{|}~_'), re.UNICODE)
BULLET_RE = re.compile('\n*[\t]*[`]*\(')
DASH_RE = re.compile('--+')
WHITESPACE_RE = re.compile('[^\S\r\n]+')
EMPTY_SENT_RE = re.compile('[,.]\ *[.,]')
FIX_START_RE = re.compile('^[^A-Za-z]*')
FIX_PERIOD = re.compile('\.([A-Za-z])')
SECTION_HEADER_RE = re.compile('SECTION [0-9]{1,2}\.|\nSEC\.* [0-9]{1,2}\.|Sec\.* [0-9]{1,2}\.')

MODES = ['train', 'test']


class Dataset(ABC):
    def __init__(self, path):
        self.path = path

    @abstractmethod
    def preprocess(self, text):
        pass

    @abstractmethod
    def create_dataset(self):
        pass

    def write_to_file(self, mode, suffix, data_list):
        dir_path = '../data/{}'.format(ds_name)
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        with open('{}/{}.{}'.format(dir_path, mode, suffix), 'w') as filehandle:
            filehandle.writelines("%s\n" % place for place in data_list)
        generate_stats(mode, suffix, data_list)


class BillSum(Dataset):
    def __init__(self, path_pattern):
        super().__init__(path_pattern)

    def __replace_semicolon(self, text, threshold=10):
        '''
        Get rid of semicolons.
        First split text into fragments between the semicolons. If the fragment
        is longer than the threshold, turn the semicolon into a period. O.w treat
        it as a comma.
        Returns new text
        '''
        new_text = ""
        for subset in re.split(';', text):
            subset = subset.strip()  # Clear off spaces
            # Check word count
            if len(subset.split()) > threshold:
                # Turn first char into uppercase
                new_text += ". " + subset[0].upper() + subset[1:]
            else:
                # Just append with a comma
                new_text += ", " + subset

        return new_text

    def __prepare_bill_sum(self, filepath):
        amend_syns = ['amendment', 'revision', 'alteration', 'improvement', 'change', 'modification', 'adaptation',
                      'adjustment', 'edit']
        text = []
        summ = []
        random.seed(42)
        num_lines = sum(1 for line in open(filepath, 'r'))
        with open(filepath) as f:
            for line in tqdm(f, total=num_lines):
                json_line = json.loads(line)
                clean_text = self.preprocess(json_line['text'])
                clean_title = self.preprocess(json_line['title'])
                for prefix in ["To ", "A bill to "]:
                    clean_title = clean_title.replace(prefix, "")
                clean_title = clean_title.capitalize()
                clean_summ = self.preprocess(json_line['summary'])
                clean_summ = clean_summ.replace(" This bill amends", ". Amendment to")
                clean_summ = clean_summ.replace('- Amends', 'amends')
                if clean_summ.startswith('Amend'):
                    syn_replace = amend_syns[random.randint(0, len(amend_syns) - 1)].capitalize() + ' of'
                    clean_summ = clean_summ.replace(clean_summ[:clean_summ.index(' ')], syn_replace)
                if not clean_title.startswith('Amend') and clean_title[:15].lower() != clean_summ[:15].lower():
                    json_line_summ = clean_title + ' ' + clean_summ
                else:
                    json_line_summ = clean_summ
                text.append(clean_text.strip())
                summ.append(json_line_summ.strip())

        return text, summ

    def preprocess(self, text):
        text = unidecode(text).strip()
        #Single newline instance within the text
        text = re.sub('(?<![\r\n])(\r?\n|\n?\r)(?![\r\n])', ' ', text)

        #Paragraph boundaries - \n\nUPPER CASE HEADING\n\n
        text = re.sub("(\n\n[^a-z]*\s[^a-z]*\n\n)|(^.+\n\n\s*)", " ", text)

        #Multiple white spaces except newlines (To preserve paragraph boundaries)
        text = re.sub("[^\S\r\n]{2,}", " ", text)

        text = re.sub("\n\s*"," ", text)

        # Indicate section headers, we need them for features
        # text = SECTION_HEADER_RE.sub('SECTION-HEADER', text)
        # For simplicity later, remove '.' from most common acronym
        text = text.replace("U.S.", "US")
        text = text.replace('SEC.', 'Section')
        text = text.replace('Sec.', 'Section')
        text = text.replace('. gov', '.gov')
        text = USC_re.sub('USC', text)

        # Remove parantheticals because they are almost always references to laws
        # We could add a special tag, but we just remove for now
        # Note we dont get rid of nested parens because that is a complex re
        # text = PAREN_re.sub('LAWREF', text)
        text = PAREN_re.sub('', text)

        # Clean html
        text = text.replace('&lt;all&gt;', '')
        text = re.sub('&(lt;|gt;)', '', text)
        text = re.sub('nbsp([.,])', '', text)
        text = re.sub('greek-[^\s]+(,|.|$| \s[xX])?', ' ', text)
        text = re.sub(' lt[,.]', '', text)
        text = re.sub('[\s.][xX] ', '. ', text)
        # Remove annoying punctuation, that's not relevant
        text = BAD_PUNCT_RE.sub('', text)

        # Get rid of long sequences of dashes - these are formating
        text = DASH_RE.sub(' ', text)

        # removing newlines, tabs, and extra spaces.
        text = WHITESPACE_RE.sub(' ', text)

        # If we ended up with "empty" sentences - get rid of them.
        text = EMPTY_SENT_RE.sub('.', text)

        # Attempt to create sentences from bullets
        text = self.__replace_semicolon(text)

        # Fix weird period issues + start of text weirdness
        # text = re.sub('\.(?=[A-Z])', '  . ', text)
        # Get rid of anything thats not a word from the start of the text
        text = FIX_START_RE.sub('', text)
        # Sometimes periods get formatted weird, make sure there is a space between periods and start of sent
        text = FIX_PERIOD.sub(". \g<1>", text)

        # Fix quotes
        text = BULLET_RE.sub("(", text)
        text = re.sub('\n``', ' ', text)
        text = re.sub('``Section', 'Section', text)
        text = re.sub('``\(', '\(', text)
        text = text.replace('``', '"')
        text = text.replace('`', "'")
        text = text.replace('\'\'', '"')
        text = re.sub('[.]"[.]|[.]+', '.', text)
        text = text.replace("united states", "United States")

        if text.startswith('a)'):
            sub_to_replace = text[:text.index('. ') + 2]
            if sub_to_replace.count(' ') < 5:
                text = text.replace(sub_to_replace, '')
            else:
                text = text.replace('a)', '')

        # Add special punct back in
        # text = text.replace('SECTION-HEADER', '<SECTION-HEADER>')
        if text[-1] != '.':
            text = text + '.'
        return text

    def create_dataset(self):
        for mode in MODES:
            print("Preprocessing and writing data for {}".format(mode))
            text, summ = self.__prepare_bill_sum(self.path.format(mode))
            if mode is not 'test':
                train_src, val_src, train_tgt, val_tgt = train_test_split(text, summ, test_size=0.20, random_state=42)
                list(map(lambda p: self.write_to_file(mode, p[0], p[1]),
                         [('source', train_src), ('target', train_tgt)]))
                list(map(lambda p: self.write_to_file('val', p[0], p[1]), [('source', val_src), ('target', val_tgt)]))
            else:
                list(map(lambda p: self.write_to_file(mode, p[0], p[1]), [('source', text), ('target', summ)]))


class NarrativeArticles(Dataset):
    def __init__(self, path):
        super().__init__(path)

    def preprocess(self, text):
        text = unidecode(text)
        text = text.replace('( ) , ; ,', 'formula')
        text = text.replace('¥', 'Yen ')
        text = text.replace('( )', 'value ')
        text = text.replace('ε', 'Epsilon')
        text = text.replace('\n', ' ')
        text = re.sub('\s*[.]\s*', '. ', text)
        text = re.sub('\s{2,}', ' ', text)
        text = re.sub('(this|This) study',r'\1 analysis', text)
        text = re.sub('(this|This) paper', r'\1 report', text)
        return text

    def create_dataset(self):
        src_txt = pickle.load(open(self.path + 'source.pkl', "rb"))
        tgt_txt = pickle.load(open(self.path + 'target.pkl', "rb"))
        preprocessed_src = list(map(lambda line: self.preprocess(line), src_txt))
        preprocessed_tgt = list(map(lambda line: self.preprocess(line), tgt_txt))
        train_src, val_src, train_tgt, val_tgt = train_test_split(preprocessed_src, preprocessed_tgt, test_size=0.20,
                                                                  random_state=25)
        val_src, test_src, val_tgt, test_tgt = train_test_split(val_src, val_tgt, test_size=0.50, random_state=25)
        for mode in MODES:
            if mode is not 'test':
                list(map(lambda p: self.write_to_file(mode, p[0], p[1]),
                         [('source', train_src), ('target', train_tgt)]))
                list(map(lambda p: self.write_to_file('val', p[0], p[1]),
                         [('source', val_src), ('target', val_tgt)]))
            else:
                list(map(lambda p: self.write_to_file(mode, p[0], p[1]),
                         [('source', test_src), ('target', test_tgt)]))


def generate_stats(mode, suffix, data_list):
    word_size_list = [len(tokenize.word_tokenize(text)) for text in data_list]
    print(mode + '({}) avg word count: '.format(suffix) + str(np.array(word_size_list).mean()))


if __name__ == '__main__':
    ds_name = sys.argv[1]
    print('Trying to write {} dataset to disk and generate word level stats from src path'.format(ds_name))
    if ds_name == 'O4B':
        NarrativeArticles('./data_prime/').create_dataset()
