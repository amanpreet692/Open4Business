import pickle

download_links = dict(pickle.load(open('./data_prime/download_links.pkl', 'rb')))

link_count = dict()

for k, v in download_links.items():
    src = v.split('/')[2].replace('www.', '')
    link_count[src] = link_count.get(src, 0) + 1

for src in link_count:
    link_count[src] = (link_count[src] / len(download_links)) * 100

link_count = {k: v for k, v in sorted(link_count.items(), key=lambda item: item[1], reverse=True)}

print(len(download_links))

srcs = ['SCIRP', 'MDPI', 'Hindawi', 'T&F Online', 'Cogentoa', 'Others (166)']
src_url = ['scirp.org', 'mdpi.com', 'downloads.hindawi.com', 'tandfonline.com', 'cogentoa.com']
reqd_link_perc = [link_count[url] for url in src_url]
total_perc = 0.0
for perc in reqd_link_perc:
    total_perc += perc
other_perc = 100 - total_perc
reqd_link_perc.append(other_perc)
print(reqd_link_perc)

print(len(link_count.keys()))

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
plt.figure(figsize=(7, 3))
plt.rcParams.update({'font.size': 13})
plt.barh(srcs, reqd_link_perc, align='center', height=0.1, alpha=0.5, zorder=1)
sns.scatterplot(x=reqd_link_perc, y=srcs, zorder=2)
plt.xticks(np.arange(0, 50, step=10))
plt.xlabel('Percent')
plt.ylabel('Source')
plt.title('Distribution of articles by source')
plt.show()