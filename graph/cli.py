"""
CLI Entry Point - Thin layer over presentation business logic.

This CLI only handles argument parsing and output formatting.
All business logic is delegated to GraphPresenter.
"""
import sys
import json
from pathlib import Path

# Reconfigure stdout for Unicode
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Import from presentation layer
from .presentation import GraphPresenter
from .presentation.formatters import (
    format_taxonomy_summary,
    format_concerns_list,
    format_tasks_list
)


def build_graph():
    """Build graph with taxonomy and dependencies."""
    from . import Graph
    g = Graph()
    g.build_folder_taxonomy()
    g.register_taxonomy_dependencies()
    g.register_concern_targets()
    return g


def main():
    global g  # Make g accessible to print_summary
    if len(sys.argv) < 2:
        print_help()
        return

    cmd = sys.argv[1]
    g = build_graph()
    presenter = GraphPresenter(g)

    if cmd == "--summary":
        # Use the original graph module for backward compatibility summary
        from . import graph as original_graph
        s = original_graph.summary()
        print_summary(s, g)  # Pass the graph reference

    elif cmd == "--taxonomy":
        summary = presenter.taxonomy.get_taxonomy_summary()
        print(json.dumps(summary['data'], indent=2, ensure_ascii=False))

    elif cmd == "--taxonomy-text":
        summary = presenter.taxonomy.get_taxonomy_summary()
        print(format_taxonomy_summary(summary['data']))

    elif cmd == "--concerns":
        args = sys.argv[2:]
        if args and args[0] in ['--domain', '--severity', '--top']:
            summary = presenter.concerns.get_top_concerns(10)
            print(json.dumps(summary['data'], indent=2, ensure_ascii=False))
        else:
            summary = presenter.concerns.get_top_concerns(10)
            print(format_concerns_list(summary['data']))

    elif cmd == "--tasks":
        summary = presenter.tasks.get_pending_tasks()
        print(json.dumps(summary['data'], indent=2, ensure_ascii=False))

    elif cmd == "--tasks-text":
        summary = presenter.tasks.get_pending_tasks()
        print(format_tasks_list(summary['data']))

    elif cmd == "--cycles":
        cycles = presenter.dependencies.get_cycles()
        if cycles['data']:
            print(f"Detected cycles: {cycles['data']}")
        else:
            print("No cycles detected")

    elif cmd == "--topo":
        order = presenter.dependencies.get_topological_order()
        print(json.dumps(order['data'], indent=2, ensure_ascii=False))

    elif cmd == "--node":
        if len(sys.argv) < 3:
            print("Usage: --node <node_id>")
            return
        node_id = sys.argv[2]
        detail = presenter.taxonomy.get_node_detail(node_id)
        print(json.dumps(detail['data'], indent=2, ensure_ascii=False))

    elif cmd == "--html":
        # Generate HTML dashboard using older graph.build_taxonomy() format
        taxonomy = g.build_taxonomy()
        html = generate_taxonomy_html(taxonomy)
        print(html)

    elif cmd == "--save-taxonomy":
        out = g.save_taxonomy_json()
        print(f"Taxonomy saved to {out}")

    elif cmd == "--help" or cmd == "-h":
        print_help()

    else:
        print(f"Unknown command: {cmd}")
        print_help()


def print_help():
    print("Usage: python -m graph.cli [OPTIONS]")
    print()
    print("Taxonomy Commands:")
    print("  --summary              Print graph summary report")
    print("  --taxonomy             JSON taxonomy summary")
    print("  --taxonomy-text        Text taxonomy summary")
    print("  --node <id>            Get node details")
    print()
    print("Concern Commands:")
    print("  --concerns             List top concerns (text format)")
    print("  --concerns --json      List top concerns (JSON format)")
    print()
    print("Task Commands:")
    print("  --tasks                Pending tasks (JSON)")
    print("  --tasks-text           Pending tasks (text format)")
    print()
    print("Dependency Commands:")
    print("  --cycles               Detect cycles")
    print("  --topo                 Topological order")
    print()
    print("Export Commands:")
    print("  --html                 Generate interactive HTML dashboard")
    print("  --save-taxonomy          Export taxonomy to JSON")


def print_summary(s, graph_ref=None):
    print("=" * 60)
    print("  DEPENDENCY GRAPH SUMMARY")
    print("=" * 60)
    print(f"  Total nodes: {s['total_nodes']}")
    print(f"  Total edges: {s['total_edges']}")
    print()
    print("  Nodes by type:")
    for t, count in sorted(s['by_type'].items()):
        print(f"    {t}: {count}")
    print()
    print("  Top 10 most-impactful items:")
    if graph_ref:
        for nid, count in s.get('top_10_impact', []):
            n = graph_ref.get_node(nid) if hasattr(graph_ref, 'get_node') else None
            title = n.get("title", "") if n else ""
            print(f"    {nid}: {count} dependents ({title})")
    print("=" * 60)


# Keep the existing HTML generation for compatibility
def generate_taxonomy_html(taxonomy):
    """Generate interactive HTML dashboard from taxonomy data."""
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
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%); color: #e4e4ef; min-height: 100vh; padding: 20px; }
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
                    <div class="chart-wrapper"><h3>Issues by Layer</h3><canvas id="layerChart"></canvas></div>
                    <div class="chart-wrapper"><h3>Severity Distribution</h3><canvas id="severityChart"></canvas></div>
                </div>
                <div id="mermaid-container"><div id="mermaid-diagram" class="mermaid"></div></div>
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


if __name__ == "__main__":
    main()