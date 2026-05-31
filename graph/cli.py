import sys
import json
from . import graph


def generate_taxonomy_html(taxonomy):
    """Generate interactive HTML dashboard from taxonomy data."""
    # Build layer nodes for mermaid
    layer_labels = {
        "L3_network": "Network (L3)",
        "L4_transport": "Transport (L4)",
        "L5_session": "Session (L5)",
        "L6_presentation": "Presentation (L6)",
        "L7_protocols": "Protocols (L7)"
    }
    
    layer_lines = []
    for layer in ["L3_network", "L4_transport", "L5_session", "L6_presentation", "L7_protocols"]:
        stats = taxonomy["layer_statistics"].get(layer, {})
        total = stats.get("total", len(taxonomy["primary_taxonomy"].get(layer, {}).get("nodes", [])))
        label = layer_labels.get(layer, layer)
        layer_lines.append(f"{layer}[\"{label} - {total}\"]")
    
    cross_lines = []
    for domain in ["security", "observability", "testing", "devops", "wiring_di", "gateway_sdk"]:
        nodes = taxonomy["cross_cutting_domains"].get(domain, {}).get("nodes", [])
        if nodes:
            cross_lines.append(f"{domain}[\"{domain} - {len(nodes)}\"]")
    
    layer_diagram = "\n        ".join(layer_lines)
    cross_diagram = "\n        ".join(cross_lines)
    
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Protocol Communication Fabric - Architecture Taxonomy</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs" type="module"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
            color: #e4e4ef; min-height: 100vh; padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header { text-align: center; margin-bottom: 30px; }
        h1 { font-size: 2.5rem; background: linear-gradient(90deg, #7c3aed, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px; }
        .subtitle { color: #94a3b8; font-size: 1.1rem; }
        .dashboard { display: grid; grid-template-columns: 300px 1fr; gap: 20px; margin-bottom: 20px; }
        .sidebar { background: rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; }
        .sidebar h2 { font-size: 1.2rem; margin-bottom: 15px; color: #06b6d4; }
        .layer-item, .domain-item { padding: 12px; margin-bottom: 8px; background: rgba(255,255,255,0.03); border-radius: 8px; cursor: pointer; transition: all 0.2s; border-left: 4px solid transparent; }
        .layer-item:hover, .domain-item:hover { background: rgba(255,255,255,0.08); transform: translateX(5px); }
        .layer-name { font-weight: 600; font-size: 1rem; }
        .layer-stats { font-size: 0.85rem; color: #94a3b8; margin-top: 5px; }
        .main-content { background: rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; }
        .chart-container { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .chart-wrapper { background: rgba(0,0,0,0.2); border-radius: 8px; padding: 15px; }
        .chart-wrapper h3 { font-size: 1rem; margin-bottom: 10px; color: #06b6d4; text-align: center; }
        #mermaid-container { background: rgba(0,0,0,0.2); border-radius: 8px; padding: 20px; min-height: 300px; margin-top: 20px; }
        .detail-panel { margin-top: 20px; background: rgba(0,0,0,0.2); border-radius: 8px; padding: 20px; max-height: 400px; overflow-y: auto; }
        .detail-panel h3 { color: #7c3aed; margin-bottom: 15px; }
        .node-item { padding: 10px; margin-bottom: 8px; background: rgba(255,255,255,0.03); border-radius: 6px; font-size: 0.9rem; }
        .severity-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; margin-left: 8px; }
        .severity-critical { background: #dc2626; color: white; }
        .severity-high { background: #ea580c; color: white; }
        .severity-medium { background: #ca8a04; color: white; }
        .severity-low { background: #16a34a; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Multi-Protocol Communication Fabric</h1>
            <p class="subtitle">Architectural Taxonomy Dashboard - OSI L3 to L7</p>
        </header>
        
        <div class="dashboard">
            <div class="sidebar">
                <h2>OSI Layers</h2>
                <div id="layers-list">Loading...</div>
                <h2 style="margin-top: 20px;">Cross-Cutting</h2>
                <div id="domains-list">Loading...</div>
            </div>
            
            <div class="main-content">
                <div class="chart-container">
                    <div class="chart-wrapper">
                        <h3>Issues by Layer</h3>
                        <canvas id="layerChart"></canvas>
                    </div>
                    <div class="chart-wrapper">
                        <h3>Severity Distribution</h3>
                        <canvas id="severityChart"></canvas>
                    </div>
                </div>
                
                <div id="mermaid-container">
                    <div id="mermaid-diagram" class="mermaid"></div>
                </div>
            </div>
        </div>
        
        <div class="detail-panel" id="detail-panel">
            <h3>Select a layer or domain to view details</h3>
            <div id="node-details"></div>
        </div>
    </div>

    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({ startOnLoad: true, theme: 'dark' });

        const diagram = `graph TD
    subgraph LAYERS ["OSI Layers"]
        ''' + layer_lines[0] + '''
        ''' + layer_lines[1] + '''
        ''' + layer_lines[2] + '''
        ''' + layer_lines[3] + '''
        ''' + layer_lines[4] + '''
    end
    subgraph CROSS_CUTTING ["Cross-Cutting"]
        ''' + cross_lines[0] + '''
        ''' + cross_lines[1] + '''
        ''' + cross_lines[2] + '''
        ''' + cross_lines[3] + '''
        ''' + cross_lines[4] + '''
        ''' + cross_lines[5] + '''
    end
    L3_network --> L4_transport
    L4_transport --> L5_session
    L5_session --> L6_presentation
    L6_presentation --> L7_protocols`;

        document.getElementById('mermaid-diagram').textContent = diagram;

        fetch('architecture_taxonomy.json')
            .then(r => r.json())
            .then(data => { renderLayers(data); renderCharts(data); mermaid.run(); })
            .catch(() => { document.getElementById('layers-list').innerHTML = 'Failed to load'; });

        function renderLayers(data) {
            let html = '';
            for (const [key, layer] of Object.entries(data.primary_taxonomy)) {
                const stats = data.layer_statistics[key] || {};
                html += '<div class="layer-item" onclick="showDetails(\'' + key + '\', \'layer\')"><div class="layer-name">' + key + '</div><div class="layer-stats">' + layer.nodes.length + ' issues</div></div>';
            }
            document.getElementById('layers-list').innerHTML = html;
            
            html = '';
            for (const [key, domain] of Object.entries(data.cross_cutting_domains)) {
                if (domain.nodes.length > 0) {
                    html += '<div class="domain-item" onclick="showDetails(\'' + key + '\', \'domain\')"><div class="layer-name">' + key + '</div><div class="layer-stats">' + domain.nodes.length + ' issues</div></div>';
                }
            }
            document.getElementById('domains-list').innerHTML = html;
        }

        function renderCharts(data) {
            const layerCtx = document.getElementById('layerChart').getContext('2d');
            const layerData = Object.entries(data.primary_taxonomy).map(([k, v]) => ({label: k, count: v.nodes.length}));
            
            new Chart(layerCtx, {
                type: 'bar',
                data: { labels: layerData.map(d => d.label), datasets: [{data: layerData.map(d => d.count), backgroundColor: ['#06b6d4', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981']}]},
                options: { responsive: true, plugins: { legend: { display: false }}, scales: { y: { beginAtZero: true }}}}
            });

            const allNodes = [];
            for (const layer of Object.values(data.primary_taxonomy)) allNodes.push(...layer.nodes);
            for (const domain of Object.values(data.cross_cutting_domains)) allNodes.push(...domain.nodes);
            const sev = { critical: 0, high: 0, medium: 0, low: 0 };
            for (const n of allNodes) { if (sev[n.severity]!==undefined) sev[n.severity]++; }

            new Chart(document.getElementById('severityChart').getContext('2d'), {
                type: 'doughnut',
                data: { labels: ['Critical', 'High', 'Medium', 'Low'], datasets: [{data: [sev.critical, sev.high, sev.medium, sev.low], backgroundColor: ['#dc2626', '#ea580c', '#ca8a04', '#16a34a']}]},
                options: { responsive: true, plugins: { legend: { position: 'bottom' }}}
            });
        }

        window.showDetails = function(key, type) {
            fetch('architecture_taxonomy.json')
                .then(r => r.json())
                .then(data => {
                    const src = type === 'layer' ? data.primary_taxonomy[key] : data.cross_cutting_domains[key];
                    document.getElementById('node-details').innerHTML = src.nodes.map(n => 
                        '<div class="node-item"><strong>' + n.id + '</strong> ' + n.title + '<span class="severity-badge severity-' + n.severity + '">' + n.severity + '</span></div>'
                    ).join('');
                });
        };
    </script>
</body>
</html>'''
    return html


if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def main():
    if len(sys.argv) < 2:
        print_help()
        return

    cmd = sys.argv[1]

    if cmd == "--summary":
        s = graph.summary()
        print_summary(s)

    elif cmd == "--query" and len(sys.argv) >= 4:
        qtype = sys.argv[2]
        qid = sys.argv[3]
        if qtype == "node":
            n = graph.get_node(qid)
            if n:
                print(json.dumps(n, indent=2, ensure_ascii=False))
            else:
                print(f"Node '{qid}' not found")
        elif qtype == "deps":
            deps = graph.get_dependencies(qid)
            print(f"Dependencies of {qid} ({len(deps)}):")
            for d in deps:
                print(f"  {d['id']} ({d['type']}, {d['severity']})")
        elif qtype == "depends":
            deps = graph.get_dependents(qid)
            print(f"Depended by {qid} ({len(deps)}):")
            for d in deps:
                print(f"  {d['id']} ({d['type']}, {d['severity']})")
        elif qtype == "impact":
            result = graph.impact_analysis(qid)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif qtype == "find":
            q = qid.lower()
            results = [n for n in graph.nodes.values()
                       if q in n.get("title", "").lower()
                       or q in n.get("id", "").lower()
                       or q in n.get("domain", "").lower()]
            for n in results:
                print(f"  {n['id']:20s}  {n.get('title', ''):50s}  [{n.get('severity', '')}]")
            print(f"  ({len(results)} matches)")
        else:
            print(f"Unknown query type: {qtype}")

    elif cmd == "--save":
        path = sys.argv[2] if len(sys.argv) > 2 else "graph_export.json"
        p = graph.save(path)
        print(f"Graph exported to {p}")

    elif cmd == "--severity":
        sev = sys.argv[2] if len(sys.argv) > 2 else "high"
        nodes = graph.get_all_by_severity(sev)
        print(f"Nodes with severity '{sev}': {len(nodes)}")
        for n in nodes:
            print(f"  {n['id']}: {n['title']} ({n['domain']})")

    elif cmd == "--domain":
        dom = sys.argv[2] if len(sys.argv) > 2 else ""
        nodes = graph.get_all_by_domain(dom)
        print(f"Nodes in domain '{dom}': {len(nodes)}")
        for n in nodes:
            print(f"  {n['id']}: {n['title']} [{n['severity']}]")

    elif cmd == "--cycles":
        domain = sys.argv[2] if len(sys.argv) > 2 else None
        cycles = graph.detect_cycles(domain)
        if cycles:
            print(f"Detected {len(cycles)} cycle(s):")
            for i, cycle in enumerate(cycles, 1):
                print(f"  Cycle {i}: {' -> '.join(cycle)}")
        else:
            print("No cycles detected")

    elif cmd == "--topo":
        domain = sys.argv[2] if len(sys.argv) > 2 else None
        order = graph.topological_sort(domain)
        print(f"Topological order ({len(order)} nodes):")
        for nid in order:
            if isinstance(nid, dict) and "__cycle__" in nid:
                cycles = nid.get("cycles", [])
                print(f"  [CYCLE] {nid['__cycle__']}")
                for cycle in cycles:
                    print(f"    {' -> '.join(cycle)}")
            else:
                print(f"  {nid}")

    elif cmd == "--critical":
        chain = graph.get_critical_path()
        print(f"Critical path ({len(chain)} nodes):")
        for nid in chain:
            n = graph.get_node(nid)
            if n:
                print(f"  {nid}: {n.get('title', '')} [{n.get('severity', '')}]")

    elif cmd == "--taxonomy":
        taxonomy = graph.build_taxonomy()
        print(json.dumps(taxonomy, indent=2, ensure_ascii=False))

    elif cmd == "--mermaid-taxonomy":
        print(graph.build_mermaid_taxonomy())

    elif cmd == "--folder-taxonomy":
        g = Graph().build_folder_taxonomy()
        print(json.dumps(g.taxonomy_summary(), indent=2, ensure_ascii=False))

    elif cmd == "--mermaid-folder-taxonomy":
        g = Graph().build_folder_taxonomy()
        print(g.build_mermaid_folder_taxonomy())

    elif cmd == "--domain-deps" and len(sys.argv) >= 3:
        g = Graph().build_folder_taxonomy().register_taxonomy_dependencies()
        domain_id = sys.argv[2]
        analysis = g.analyze_domain_dependencies(domain_id)
        print(f"Domain {domain_id}:")
        print(f"  Total files: {analysis['total_files']}")
        print(f"  Internal dependencies: {len(analysis['internal_dependencies'])} nodes")
        print(f"  External dependencies: {len(analysis['external_dependencies'])} nodes")

    elif cmd == "--registry" and len(sys.argv) >= 3:
        g = Graph().build_folder_taxonomy().register_taxonomy_dependencies().build_dependency_registry()
        domain_id = sys.argv[2] if len(sys.argv) > 2 else None
        
        if domain_id:
            # Filter by domain
            domain_rels = [r for r in g.dependency_registry if r["source"].startswith(domain_id.rstrip('.'))]
            print(f"Dependency Registry for {domain_id}: {len(domain_rels)} relationships")
            for rel in domain_rels[:20]:
                src_name = g.taxonomy_nodes[rel["source"]]["name"]
                tgt_name = g.taxonomy_nodes[rel["target"]]["name"] if rel["target"] in g.taxonomy_nodes else "unknown"
                print(f"  {rel['source']} ({src_name}) -> {rel['target']} ({tgt_name})")
        else:
            print(f"Full Dependency Registry: {len(g.dependency_registry)} relationships")

    elif cmd == "--html":
        # Show internal deps detail
        for fid, deps in list(analysis['internal_dependencies'].items())[:5]:
            fname = g.taxonomy_nodes[fid]['name']
            dep_names = [g.taxonomy_nodes[d]['name'] for d in deps]
            print(f"    {fid}: {fname} -> {', '.join(dep_names)}")

    elif cmd == "--html":
        taxonomy = graph.build_taxonomy()
        html = generate_taxonomy_html(taxonomy)
        print(html)

    elif cmd == "--save":
        path = sys.argv[2] if len(sys.argv) > 2 else "graph_export.json"
        p = graph.save(path)
        print(f"Graph exported to {p}")

    else:
        print_help()


def print_help():
    print("Usage: python -m graph.cli [OPTIONS]")
    print()
    print("  --summary                    Print summary report")
    print("  --query node <id>            Get node details")
    print("  --query deps <id>            Get what X depends on")
    print("  --query depends <id>         Get what depends on X")
    print("  --query impact <id>          Recursive impact analysis")
    print("  --severity <level>           List nodes by severity")
    print("  --domain <domain>            List nodes by domain")
    print("  --topo [domain]              Topological sort (optionally by domain)")
    print("  --cycles [domain]            Detect cycle(s) (optionally by domain)")
    print("  --critical                   Show critical path chain")
    print("  --taxonomy                   Show architectural taxonomy (OSI layers)")
    print("  --mermaid-taxonomy           Generate Mermaid diagram for taxonomy")
    print("  --folder-taxonomy            Build tax from CSVs (domains/subdomains/files)")
    print("  --mermaid-folder-taxonomy    Mermaid diagram from folder taxonomy")
    print("  --domain-deps <domain_id>    Analyze dependencies for a domain")
    print("  --registry [domain_id]       Show dependency relationships (optional domain filter)")
    print("  --html                       Generate interactive HTML dashboard")
    print("  --save [path]                Export graph to JSON (default: graph_export.json)")


def print_summary(s):
    print("=" * 60)
    print("  DEPENDENCY GRAPH SUMMARY")
    print("=" * 60)
    print(f"  Total nodes: {s['total_nodes']}")
    print(f"  Total edges: {s['total_edges']}")
    print()
    print("  Nodes by type:")
    for t, count in sorted(s["by_type"].items()):
        print(f"    {t}: {count}")
    print()
    print("  Nodes by severity:")
    for sev, count in sorted(s["by_severity"].items()):
        print(f"    {sev}: {count}")
    print()
    print("  Nodes by domain:")
    for dom, count in sorted(s["by_domain"].items()):
        print(f"    {dom}: {count}")
    print()
    print("  Top 10 most-impactful items (most dependents):")
    for nid, count in s["top_10_impact"]:
        n = graph.get_node(nid)
        title = n.get("title", "") if n else ""
        print(f"    {nid}: {count} dependents  ({title})")
    print()
    print(f"  Critical path ({len(s['critical_path'])} nodes):")
    if s["critical_path"]:
        for nid in s["critical_path"]:
            n = graph.get_node(nid)
            if n:
                print(f"    {nid}: {n.get('title', '')} [{n.get('severity', '')}]")
    else:
        print("    (none)")
    print("=" * 60)


if __name__ == "__main__":
    main()
