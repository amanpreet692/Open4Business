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
