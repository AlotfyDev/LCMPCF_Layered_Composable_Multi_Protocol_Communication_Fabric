#!/usr/bin/env python
"""Debug architecture taxonomy."""
import json
from graph import Graph

g = Graph()
# First build() populates self.nodes from CSV files
g.build()

print('Node domains in self.nodes:')
domains_seen = {}
for nid, node in list(g.nodes.items())[:10]:
    dom = node.get('domain', '')
    nt = node.get('type', '')
    print(f'  {nid}: type={nt}, domain={dom}')

print()
print('Total nodes:', len(g.nodes))
print()
print('Unique domains:')
all_domains = set(node.get('domain', '') for node in g.nodes.values())
for d in sorted(all_domains):
    count = sum(1 for n in g.nodes.values() if n.get('domain') == d)
    print(f'  {d}: {count}')