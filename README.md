
# Open4Business (O4B)
Code for the paper [Open4Business(O4B): An Open Access Dataset for Summarizing Business Documents](https://arxiv.org/abs/2011.07636) accepted in the Workshop for Dataset Curation and Security at NeurIPS-2020. 

A summarization dataset consisting of over 17k GOLD Open Access business journal articles.

The current version of the dataset can be downloaded from: [O4B Download](https://drive.google.com/file/d/1w5mc6vxXrHIPRbRpoOxbUo8yTdVkW6l5/view?usp=sharing).

Steps to use the dataset:

 1. Download the zip from the URL given above and extract it.
 2. The extracted directory will contain 7 files - 1 source and 1 target file for each of the splits, namely train, dev and test. For instance, for training set the file names will be train.source and train.target. The additional file called refs.bib consist of the bibtex reference for the articles used for creating O4B. 
 3. In both the source and target files, each line represents 1 record. 
 4. These files can be used for training new summarization models directly!
 
For benchmarking experiments, following resources were used:
1. Models from Hugging Face - [T5-base](https://huggingface.co/t5-base) and [distillBART](https://huggingface.co/sshleifer/distilbart-cnn-12-6)
2. For benchmarking the above models use these [steps](https://github.com/huggingface/transformers/tree/master/examples/seq2seq).
Please refer to HuggingFace documentation for any issues with fine-tuning the models.

For code re-use, refer [this](DatasetGeneration.md).
