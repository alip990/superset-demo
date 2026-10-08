#!/usr/bin/env python3
"""Version-pinned, reproducible source evidence; never claims runtime success."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

FILES = [
    'superset-frontend/webpack.config.js',
    'superset-frontend/src/extensions/ExtensionsStartup.tsx',
    'superset-frontend/src/extensions/ExtensionsLoader.ts',
    'superset-frontend/packages/superset-core/src/index.ts',
    'superset-frontend/packages/superset-core/src/extensions/index.ts',
    'superset-frontend/packages/superset-ui-core/src/ui-overrides/ExtensionsRegistry.ts',
    'superset-frontend/packages/superset-ui-core/src/ui-overrides/types.ts',
    'superset-frontend/src/filters/components/Time/TimeFilterPlugin.tsx',
    'superset-frontend/src/embedded/index.tsx',
    'superset/extensions/discovery.py',
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', default='6.1.0')
    parser.add_argument('--output', type=Path, default=Path('build/host-audit'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    def fetch(path):
        url = f'https://raw.githubusercontent.com/apache/superset/{args.tag}/{path}'
        data = urllib.request.urlopen(url, timeout=60).read()
        target = args.output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return path, data.decode(), {'url': url, 'sha256': hashlib.sha256(data).hexdigest()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        sources = list(pool.map(fetch, FILES))
    text = {path: contents for path, contents, _ in sources}
    releases = json.load(urllib.request.urlopen(
        'https://api.github.com/repos/apache/superset/releases?per_page=100', timeout=60))
    stable = [r['tag_name'] for r in releases if not r['prerelease']
              and r['tag_name'][0].isdigit()]
    webpack = text[FILES[0]]
    federation = webpack[webpack.index('new ModuleFederationPlugin'):]
    federation = federation[:federation.index('\n  }),')]
    report = {
        'tag': args.tag, 'stable_releases': stable,
        'source': {path: meta for path, _, meta in sources},
        'host_shares_ui_core': "'@superset-ui/core'" in federation,
        'public_extensions_exposes_registry': 'getExtensionsRegistry' in text[FILES[4]],
        'native_consumer_uses_internal_registry': 'getExtensionsRegistry' in text[FILES[7]],
        'embedded_initializes_extensions': any(word in text[FILES[8]] for word in
                                               ('ExtensionsStartup', 'ExtensionsLoader')),
        'runtime_proven': False,
    }
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'source'}, indent=2))

if __name__ == '__main__':
    main()
