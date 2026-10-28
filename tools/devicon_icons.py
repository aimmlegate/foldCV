"""Fetch pinned Devicon SVGs, render their PNGs and write the icon pack of the bundled template.

  .venv/bin/python -I tools/devicon_icons.py fetch   # network: devicon.json snapshot and missing SVGs at REVISION
  .venv/bin/python -I tools/devicon_icons.py build   # offline: PNGs, pinned-sources.json and technology-icons.json

The pack holds every Devicon icon at REVISION that has a usable SVG. ICONS and NAMED give hand-written ids and names;
the other icons come from the devicon.json snapshot, named by their Devicon name and altnames. PNGs: resvg-py 0.5.0,
original colors; the ICONS of template 2.5.0 keep the longer side 384 px, later icons use 192 px to keep the pack small.
devicon/sources.json keeps only the first eleven: the frozen foldcv-reference manifest pins its bytes. The template gets
one pack asset, since a portable archive holds at most 47 entries and each captured asset is one of them.
"""

import base64
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEVICON = ROOT / 'skills/format-resume/assets/devicon'
TEMPLATE = ROOT / 'templates/bundled/assets'
REPOSITORY = 'https://github.com/devicons/devicon'
RELEASE = 'v2.18.0'
REVISION = 'ff435a0fff0391aefbf70d63a3fe7cfe64f82df0'
BASE = 'https://raw.githubusercontent.com/devicons/devicon/' + REVISION + '/'
RAW = BASE + 'icons/'
SNAPSHOT = DEVICON / 'devicon.json'
SNAPSHOT_SHA256 = 'c23c643f14bf5031c994c0d225d51f4562c76a0a957d9d650e06449779ee1d33'
# Variant chosen per snapshot icon by fetch (null: no variant without <text or <image).
VARIANTS = DEVICON / 'variants.json'
SIDE = 384
NEW_SIDE = 192

# Icon id (the canonical id of packages/resume_core/technologies.py where it has one), Devicon icon, variant and the
# names the template adds. Catalog synonyms (k8s, gitlab ci, postgres) bind through the catalog when a name is looked
# up; names here cover technologies outside the catalog and icon-only spellings.
ICONS = [
    ('python', 'python', 'original', []), ('golang', 'go', 'original', ['go']), ('java', 'java', 'original', []),
    ('javascript', 'javascript', 'original', []), ('typescript', 'typescript', 'original', []),
    ('csharp', 'csharp', 'original', []), ('cplusplus', 'cplusplus', 'original', ['cpp']), ('c', 'c', 'original', []),
    ('php', 'php', 'original', []), ('ruby', 'ruby', 'original', []), ('kotlin', 'kotlin', 'original', []),
    ('swift', 'swift', 'original', []), ('rust', 'rust', 'original', []), ('scala', 'scala', 'original', []),
    ('bash', 'bash', 'original', ['sh']), ('powershell', 'powershell', 'original', []), ('html', 'html5', 'original', []),
    ('css', 'css3', 'original', []), ('dart', 'dart', 'original', []),
    ('objectivec', 'objectivec', 'plain', ['objective-c', 'objective c', 'objc']), ('perl', 'perl', 'original', []),
    ('r', 'r', 'original', []),
    ('dotnet', 'dot-net', 'original', ['.net и .net framework']), ('django', 'django', 'plain', []),
    ('djangorest', 'djangorest', 'original', ['drf']), ('fastapi', 'fastapi', 'original', []),
    ('flask', 'flask', 'original', []), ('spring', 'spring', 'original', []),
    ('react', 'react', 'original', ['react native']), ('vue', 'vuejs', 'original', []),
    ('angular', 'angular', 'original', []), ('nodejs', 'nodejs', 'original', ['node']),
    ('express', 'express', 'original', ['express.js', 'expressjs']), ('nestjs', 'nestjs', 'original', ['nest.js']),
    ('nextjs', 'nextjs', 'original', ['next.js']), ('nuxt', 'nuxtjs', 'original', ['nuxt.js', 'nuxtjs']),
    ('laravel', 'laravel', 'original', []), ('symfony', 'symfony', 'original', []), ('rails', 'rails', 'plain', []),
    ('yii', 'yii', 'original', []), ('pandas', 'pandas', 'original', []), ('numpy', 'numpy', 'original', []),
    ('pytorch', 'pytorch', 'original', []), ('tensorflow', 'tensorflow', 'original', []),
    ('sqlalchemy', 'sqlalchemy', 'original', []), ('qt', 'qt', 'original', []), ('unity', 'unity', 'original', []),
    ('unreal', 'unrealengine', 'original', []), ('grpc', 'grpc', 'plain', []), ('graphql', 'graphql', 'plain', []),
    ('flutter', 'flutter', 'original', []), ('jquery', 'jquery', 'original', []),
    ('redux', 'redux', 'original', ['redux toolkit']),
    ('svelte', 'svelte', 'original', ['sveltekit']), ('bootstrap', 'bootstrap', 'original', []),
    ('tailwindcss', 'tailwindcss', 'original', ['tailwind css', 'tailwind']), ('sass', 'sass', 'original', ['scss']),
    ('postgresql', 'postgresql', 'original', []), ('mysql', 'mysql', 'original', []),
    ('mariadb', 'mariadb', 'original', []), ('mongodb', 'mongodb', 'original', []), ('redis', 'redis', 'original', []),
    ('elasticsearch', 'elasticsearch', 'original', []), ('sqlite', 'sqlite', 'original', []),
    ('oracle', 'oracle', 'original', []), ('mssql', 'microsoftsqlserver', 'plain', []),
    ('clickhouse', 'clickhouse', 'original', []), ('cassandra', 'cassandra', 'original', []),
    ('couchdb', 'couchdb', 'original', ['apache couchdb']), ('neo4j', 'neo4j', 'original', []),
    ('dynamodb', 'dynamodb', 'original', ['amazon dynamodb', 'aws dynamodb']), ('influxdb', 'influxdb', 'original', []),
    ('memcached', 'memcached', 'original', []), ('kafka', 'apachekafka', 'original', []),
    ('rabbitmq', 'rabbitmq', 'original', []), ('nats', 'nats', 'original', ['nats.io']),
    ('aws', 'amazonwebservices', 'original', []), ('azure', 'azure', 'original', []),
    ('gcp', 'googlecloud', 'original', []), ('digitalocean', 'digitalocean', 'original', ['digital ocean']),
    ('heroku', 'heroku', 'original', []), ('cloudflare', 'cloudflare', 'original', []),
    ('firebase', 'firebase', 'original', ['google firebase']),
    ('git', 'git', 'original', []), ('github', 'github', 'original', []),
    ('githubactions', 'githubactions', 'original', ['github actions']), ('gitlab', 'gitlab', 'original', []),
    ('bitbucket', 'bitbucket', 'original', ['atlassian bitbucket']), ('jenkins', 'jenkins', 'original', []),
    ('teamcity', 'teamcity', 'original', []), ('bamboo', 'bamboo', 'original', []),
    ('circleci', 'circleci', 'plain', ['circle ci']), ('argocd', 'argocd', 'original', []),
    ('azuredevops', 'azuredevops', 'original', ['azure devops']),
    ('docker', 'docker', 'original', ['docker compose', 'docker-compose', 'docker swarm']),
    ('kubernetes', 'kubernetes', 'original', []), ('helm', 'helm', 'original', []),
    ('terraform', 'terraform', 'original', []), ('ansible', 'ansible', 'original', []),
    ('vagrant', 'vagrant', 'original', []), ('packer', 'packer', 'original', ['hashicorp packer']),
    ('vault', 'vault', 'original', []), ('consul', 'consul', 'original', []), ('podman', 'podman', 'original', []),
    ('openstack', 'openstack', 'original', []), ('nginx', 'nginx', 'original', []), ('apache', 'apache', 'original', []),
    ('traefik', 'traefikproxy', 'original', []), ('linux', 'linux', 'original', []), ('ubuntu', 'ubuntu', 'original', []),
    ('debian', 'debian', 'original', []), ('centos', 'centos', 'original', []), ('rhel', 'redhat', 'original', []),
    ('windows', 'windows11', 'original', []),
    ('prometheus', 'prometheus', 'original', []), ('grafana', 'grafana', 'original', []),
    ('kibana', 'kibana', 'original', []), ('logstash', 'logstash', 'original', []),
    ('opentelemetry', 'opentelemetry', 'original', []), ('sentry', 'sentry', 'original', []),
    ('datadog', 'datadog', 'original', []), ('newrelic', 'newrelic', 'original', ['new relic']),
    ('jira', 'jira', 'original', ['atlassian jira']), ('confluence', 'confluence', 'original', ['atlassian confluence']),
    ('figma', 'figma', 'original', []),
    ('pytest', 'pytest', 'original', []), ('jest', 'jest', 'plain', []), ('selenium', 'selenium', 'original', []),
    ('junit', 'junit', 'original', []), ('postman', 'postman', 'original', []), ('cypress', 'cypressio', 'original', []),
    ('playwright', 'playwright', 'original', []),
    ('maven', 'maven', 'original', []), ('gradle', 'gradle', 'original', []), ('npm', 'npm', 'original', []),
    ('yarn', 'yarn', 'original', []), ('webpack', 'webpack', 'original', []), ('vite', 'vitejs', 'original', []),
    ('jupyter', 'jupyter', 'original', ['jupyter notebook', 'jupyterlab']), ('airflow', 'apacheairflow', 'original', []),
    ('spark', 'apachespark', 'original', ['pyspark']), ('hadoop', 'hadoop', 'original', []),
]
# Hand-written ids and names of later icons (UI-FEEDBACK J), rendered at NEW_SIDE; ICONS and NAMED override
# the entries built from the devicon.json snapshot.
NAMED = [
    ('haproxy', 'haproxy', 'original', []), ('openapi', 'openapi', 'original', []), ('oauth', 'oauth', 'original', []),
    ('vmware', 'vsphere', 'original', []), ('proxmox', 'proxmox', 'original', []), ('ceph', 'ceph', 'original', []),
    ('istio', 'istio', 'original', []), ('envoy', 'envoy', 'original', ['envoy proxy']),
    ('loki', 'grafanaloki', 'original', []), ('jaeger', 'jaegertracing', 'original', []),
    ('entityframework', 'entityframeworkcore', 'original', ['entity framework core', 'ef']),
    ('hibernate', 'hibernate', 'original', []), ('elixir', 'elixir', 'original', []),
    ('erlang', 'erlang', 'original', []), ('clojure', 'clojure', 'original', []),
    ('haskell', 'haskell', 'original', []), ('fsharp', 'fsharp', 'original', ['f#']), ('lua', 'lua', 'original', []),
    ('julia', 'julia', 'original', []), ('matlab', 'matlab', 'original', []), ('groovy', 'groovy', 'original', []),
    ('solidity', 'solidity', 'original', []), ('zig', 'zig', 'original', []), ('fortran', 'fortran', 'original', []),
    ('cobol', 'cobol', 'original', []), ('delphi', 'delphi', 'original', []),
    ('visualbasic', 'visualbasic', 'original', ['visual basic', 'vb.net']), ('latex', 'latex', 'original', []),
    ('webassembly', 'wasm', 'original', ['wasm']), ('astro', 'astro', 'original', []),
    ('solidjs', 'solidjs', 'original', ['solid.js', 'solid']), ('gatsby', 'gatsby', 'original', []),
    ('remix', 'remix', 'original', []), ('htmx', 'htmx', 'original', []),
    ('alpinejs', 'alpinejs', 'original', ['alpine.js']), ('angularjs', 'angularjs', 'original', ['angular.js']),
    ('angularmaterial', 'angularmaterial', 'original', ['angular material']),
    ('materialui', 'materialui', 'original', ['material ui', 'mui']),
    ('antdesign', 'antdesign', 'original', ['ant design', 'antd']),
    ('chakraui', 'chakraui', 'original', ['chakra ui']), ('vuetify', 'vuetify', 'original', []),
    ('shadcn', 'shadcn', 'original', ['shadcn/ui', 'shadcn ui']),
    ('styledcomponents', 'styledcomponents', 'original', ['styled-components', 'styled components']),
    ('reactrouter', 'reactrouter', 'original', ['react router']), ('rxjs', 'rxjs', 'original', []),
    ('ngrx', 'ngrx', 'original', []), ('mobx', 'mobx', 'original', []), ('zustand', 'zustand', 'original', []),
    ('axios', 'axios', 'plain', []), ('lodash', 'lodash', 'original', []),
    ('d3js', 'd3js', 'original', ['d3', 'd3.js']), ('chartjs', 'chartjs', 'original', ['chart.js']),
    ('threejs', 'threejs', 'original', ['three.js']), ('socketio', 'socketio', 'original', ['socket.io']),
    ('trpc', 'trpc', 'original', []),
    ('apollo', 'apollographql', 'original', ['apollo graphql', 'apollo client', 'apollo server']),
    ('prisma', 'prisma', 'original', []), ('typeorm', 'typeorm', 'original', []),
    ('sequelize', 'sequelize', 'original', []), ('mongoose', 'mongoose', 'original', []),
    ('fastify', 'fastify', 'original', []), ('deno', 'denojs', 'original', []), ('bun', 'bun', 'original', []),
    ('electron', 'electron', 'original', ['electron.js']), ('tauri', 'tauri', 'original', []),
    ('postcss', 'postcss', 'original', []), ('wordpress', 'wordpress', 'original', []),
    ('drupal', 'drupal', 'original', []), ('magento', 'magento', 'original', []),
    ('phoenix', 'phoenix', 'original', []), ('akka', 'akka', 'original', []), ('ktor', 'ktor', 'original', []),
    ('quarkus', 'quarkus', 'original', []), ('vertx', 'vertx', 'original', ['vert.x']),
    ('vaadin', 'vaadin', 'original', []), ('thymeleaf', 'thymeleaf', 'original', []),
    ('tomcat', 'tomcat', 'original', ['apache tomcat']), ('liquibase', 'liquibase', 'original', []),
    ('flyway', 'flyway', 'original', []), ('blazor', 'blazor', 'original', []), ('fiber', 'fiber', 'original', []),
    ('codeigniter', 'codeigniter', 'plain', []), ('cakephp', 'cakephp', 'original', []),
    ('doctrine', 'doctrine', 'original', []), ('composer', 'composer', 'original', []),
    ('nuget', 'nuget', 'original', []), ('duckdb', 'duckdb', 'original', []),
    ('couchbase', 'couchbase', 'original', []), ('cosmosdb', 'cosmosdb', 'original', ['cosmos db', 'azure cosmos db']),
    ('supabase', 'supabase', 'original', []), ('metabase', 'metabase', 'original', []),
    ('pulsaredit', 'pulsar', 'original', ['pulsar edit']), ('matplotlib', 'matplotlib', 'original', []),
    ('seaborn', 'seaborn', 'original', []), ('plotly', 'plotly', 'original', []),
    ('streamlit', 'streamlit', 'original', []), ('anaconda', 'anaconda', 'original', ['conda']),
    ('googlecolab', 'googlecolab', 'original', ['google colab', 'colab']), ('keras', 'keras', 'original', []),
    ('scikitlearn', 'scikitlearn', 'original', ['scikit-learn', 'sklearn']),
    ('huggingface', 'huggingface', 'original', ['hugging face']), ('opencv', 'opencv', 'original', []),
    ('kubeflow', 'kubeflow', 'original', []), ('ollama', 'ollama', 'original', []),
    ('nomad', 'nomad', 'original', ['hashicorp nomad']), ('pulumi', 'pulumi', 'original', []),
    ('rancher', 'rancher', 'original', []), ('portainer', 'portainer', 'original', []),
    ('harbor', 'harbor', 'original', []), ('k3s', 'k3s', 'original', []),
    ('hyperv', 'hyperv', 'original', ['hyper-v']),
    ('cloudrun', 'cloudrun', 'original', ['cloud run', 'google cloud run']),
    ('cloudflareworkers', 'cloudflareworkers', 'original', ['cloudflare workers']),
    ('netlify', 'netlify', 'original', []), ('vercel', 'vercel', 'original', []),
    ('travis', 'travis', 'original', ['travis ci', 'travisci']), ('gitea', 'gitea', 'original', []),
    ('dynatrace', 'dynatrace', 'original', []), ('fedora', 'fedora', 'original', []),
    ('archlinux', 'archlinux', 'original', ['arch linux']), ('opensuse', 'opensuse', 'original', []),
    ('rockylinux', 'rockylinux', 'original', ['rocky linux']), ('unix', 'unix', 'original', []),
    ('apple', 'apple', 'original', ['macos', 'ios']), ('wireguard', 'wireguard', 'original', []),
    ('okta', 'okta', 'original', []), ('jwt', 'jwt', 'original', []), ('swagger', 'swagger', 'original', []),
    ('android', 'android', 'original', ['android sdk']), ('expo', 'expo', 'original', []),
    ('ionic', 'ionic', 'original', []), ('capacitor', 'capacitor', 'original', []),
    ('jetpackcompose', 'jetpackcompose', 'original', ['jetpack compose']), ('realm', 'realm', 'original', []),
    ('xamarin', 'xamarin', 'original', []), ('vitest', 'vitest', 'original', []), ('mocha', 'mocha', 'original', []),
    ('cucumber', 'cucumber', 'plain', []), ('rspec', 'rspec', 'original', []),
    ('puppeteer', 'puppeteer', 'original', []), ('k6', 'k6', 'original', ['grafana k6']),
    ('gatling', 'gatling', 'original', []), ('insomnia', 'insomnia', 'original', []),
    ('browserstack', 'browserstack', 'original', []), ('testrail', 'testrail', 'original', []),
    ('sonarqube', 'sonarqube', 'original', []), ('burpsuite', 'burpsuite', 'original', ['burp suite']),
    ('kalilinux', 'kalilinux', 'original', ['kali linux', 'kali']), ('sketch', 'sketch', 'original', []),
    ('adobexd', 'xd', 'original', ['adobe xd']), ('photoshop', 'photoshop', 'original', ['adobe photoshop']),
    ('illustrator', 'illustrator', 'original', ['adobe illustrator']),
    ('aftereffects', 'aftereffects', 'original', ['adobe after effects', 'after effects']),
    ('premierepro', 'premierepro', 'original', ['adobe premiere pro', 'premiere pro']),
    ('blender', 'blender', 'original', []), ('notion', 'notion', 'original', []), ('linear', 'linear', 'plain', []),
    ('trello', 'trello', 'original', []), ('youtrack', 'youtrack', 'original', []), ('slack', 'slack', 'original', []),
    ('salesforce', 'salesforce', 'original', []), ('godot', 'godot', 'original', []),
    ('opengl', 'opengl', 'original', []), ('vulkan', 'vulkan', 'original', []), ('webgl', 'webgl', 'original', []),
    ('webgpu', 'webgpu', 'original', []), ('cmake', 'cmake', 'original', []), ('arduino', 'arduino', 'original', []),
    ('raspberrypi', 'raspberrypi', 'original', ['raspberry pi']), ('ros', 'ros', 'original', ['ros 2', 'ros2']),
    ('labview', 'labview', 'original', []), ('verilog', 'verilog', 'original', []),
    ('svn', 'subversion', 'original', ['subversion']),
    ('vscode', 'vscode', 'original', ['vs code', 'visual studio code']),
    ('visualstudio', 'visualstudio', 'original', ['visual studio']),
    ('intellij', 'intellij', 'original', ['intellij idea']), ('pycharm', 'pycharm', 'original', []),
    ('webstorm', 'webstorm', 'original', []), ('phpstorm', 'phpstorm', 'original', []),
    ('rider', 'rider', 'original', []), ('goland', 'goland', 'original', []), ('clion', 'clion', 'original', []),
    ('datagrip', 'datagrip', 'original', []), ('dbeaver', 'dbeaver', 'original', []),
    ('eclipse', 'eclipse', 'original', []), ('xcode', 'xcode', 'original', []),
    ('androidstudio', 'androidstudio', 'original', ['android studio']), ('vim', 'vim', 'original', []),
    ('neovim', 'neovim', 'original', []), ('pnpm', 'pnpm', 'original', []), ('poetry', 'poetry', 'original', []),
    ('uv', 'uv', 'original', []), ('bazel', 'bazel', 'original', []), ('babel', 'babel', 'original', []),
    ('eslint', 'eslint', 'original', []), ('rollup', 'rollup', 'original', []),
    ('storybook', 'storybook', 'original', []), ('json', 'json', 'original', []), ('yaml', 'yaml', 'original', []),
    ('markdown', 'markdown', 'original', []),
]
# Devicon altnames that name another technology too: Framer (design tool), PS (Photoshop), V.
SKIP_ALTNAMES = {'framer', 'ps', 'v'}
# The catalog keys of template revision 2.4.0, kept so a name matched before still matches.
EARLIER_KEYS = {'python': 'python', 'c#': 'csharp', '.net': 'dotnet', '.net framework': 'dotnet',
    '.net и .net framework': 'dotnet', 'docker': 'docker', 'fastapi': 'fastapi', 'django rest framework': 'djangorest',
    'django rest framework (drf)': 'djangorest', 'grafana': 'grafana', 'kibana': 'kibana', 'c++': 'cplusplus',
    'grpc': 'grpc', 'linux': 'linux'}


def url(name, variant):
    return f'{RAW}{name}/{name}-{variant}.svg'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def usable(raw):
    return b'<text' not in raw and b'<image' not in raw


def snapshot():
    raw = SNAPSHOT.read_bytes()
    if sha256(raw) != SNAPSHOT_SHA256:
        raise ValueError('devicon.json differs from its pinned hash')
    return json.loads(raw)


def normalized(name):
    sys.path.insert(0, str(ROOT))
    from packages.resume_core.technologies import normalize_name
    return normalize_name(name)


def plan():
    """Hand-written icons, then one icon per other snapshot entry. A snapshot icon whose name is already an icon id, a
    hand-written name or another catalog technology gets the id <name>-alt, so its id still names only itself."""
    sys.path.insert(0, str(ROOT))
    from packages.resume_core.technologies import resolve_technology
    entries = [(identifier, name, variant, names, SIDE) for identifier, name, variant, names in ICONS]
    entries += [(identifier, name, variant, names, NEW_SIDE) for identifier, name, variant, names in NAMED]
    used = {name for _identifier, name, *_rest in entries}
    taken = {normalized(key) for identifier, _name, _variant, names, _side in entries for key in [identifier, *names]}
    taken |= set(EARLIER_KEYS)
    auto = []
    for entry in snapshot():
        name = entry['name']
        if name in used:
            continue
        identifier = name
        if identifier in taken or resolve_technology(identifier).canonical_id not in (None, identifier):
            identifier = name + '-alt'
        if identifier in taken:
            raise ValueError('no free id for ' + name)
        taken.add(identifier)
        auto.append((identifier, name, None, [], NEW_SIDE))
    return entries, auto


def fetch():
    import ssl
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())

    def download(address):
        with urllib.request.urlopen(address, timeout=30, context=context) as reply:
            return reply.read()

    if not SNAPSHOT.exists():
        SNAPSHOT.write_bytes(download(BASE + 'devicon.json'))
    versions = {entry['name']: entry['versions']['svg'] for entry in snapshot()}
    chosen = json.loads(VARIANTS.read_text()) if VARIANTS.exists() else {}
    entries, auto = plan()
    for identifier, name, variant, _names, _side in entries + auto:
        target = DEVICON / (identifier + '.svg')
        if target.exists() or (variant is None and name in chosen):
            continue
        order = [variant] if variant else [value for value in ('original', 'plain') if value in versions[name]] + [
            value for value in versions[name] if value not in ('original', 'plain')]
        for candidate in order:
            raw = download(url(name, candidate))
            if not raw.lstrip().startswith((b'<svg', b'<?xml')):
                raise ValueError('not an SVG: ' + name)
            if usable(raw) or variant:
                target.write_bytes(raw)
                print('fetched', identifier, candidate, len(raw))
                break
        else:
            candidate = None
            print('no usable variant', name)
        if variant is None:
            chosen[name] = candidate
            VARIANTS.write_text(json.dumps(dict(sorted(chosen.items())), indent=1) + '\n')


def render(raw, side):
    import resvg_py
    from PIL import Image
    from io import BytesIO
    text = raw.decode('utf-8')
    png = bytes(resvg_py.svg_to_bytes(svg_string=text, width=side))
    with Image.open(BytesIO(png)) as image:
        if image.height > side:
            png = bytes(resvg_py.svg_to_bytes(svg_string=text, height=side))
    return png


def build():
    sys.path.insert(0, str(ROOT))
    from packages.resume_core.technologies import resolve_technology
    frozen = json.loads((DEVICON / 'sources.json').read_text())
    altnames = {entry['name']: entry['altnames'] for entry in snapshot()}
    chosen = json.loads(VARIANTS.read_text())
    entries, auto = plan()
    skipped = sorted(name for _identifier, name, *_rest in auto if chosen[name] is None)
    entries += [(identifier, name, chosen[name], [], side) for identifier, name, _variant, _names, side in auto
        if chosen[name] is not None]
    pinned, icons, names, dropped = {}, {}, dict(EARLIER_KEYS), []
    for identifier, name, variant, extra, side in entries:
        svg = (DEVICON / (identifier + '.svg')).read_bytes()
        if not usable(svg):
            raise ValueError('icon needs fonts or external images: ' + identifier)
        source = frozen.get(identifier)
        if source is None:
            png = render(svg, side)
            (DEVICON / (identifier + '.png')).write_bytes(png)
            source = pinned[identifier] = {'url': url(name, variant), 'revision': REVISION, 'release': RELEASE,
                'license': 'MIT', 'sha256': sha256(svg), 'pngSha256': sha256(png), 'rasterizer': 'resvg-py 0.5.0',
                'variant': variant, 'side': side}
        elif source['sha256'] != sha256(svg):
            raise ValueError('existing SVG differs from its recorded hash: ' + identifier)
        png = (DEVICON / (identifier + '.png')).read_bytes()
        icons[identifier] = {'source': source['url'], 'svgSha256': source['sha256'], 'sha256': sha256(png),
            'png': base64.b64encode(png).decode('ascii')}
        for key in [identifier, *extra]:
            if names.setdefault(key, identifier) != identifier:
                raise ValueError('one name binds two icons: ' + key)
    # Devicon altnames bind last: an existing binding or another catalog technology wins and the altname is dropped.
    for identifier, name, *_rest in entries:
        for alias in altnames.get(name, []):
            key = normalized(alias)
            canonical = resolve_technology(key).canonical_id
            if names.get(key) == identifier:
                continue
            if key in names or key in SKIP_ALTNAMES or canonical not in (None, identifier):
                dropped.append(f'{alias} ({identifier}; kept {names.get(key) or canonical or "none"})')
            else:
                names[key] = identifier
    (DEVICON / 'pinned-sources.json').write_text(json.dumps(pinned, indent=2) + '\n')
    (TEMPLATE / 'devicon-LICENSE.txt').write_bytes((DEVICON / 'LICENSE').read_bytes())
    pack = {'schema': 'foldcv-icon-pack-1',
        'provenance': {'upstream': REPOSITORY, 'release': RELEASE, 'commit': REVISION, 'license': 'MIT',
            'licenseFile': 'devicon-LICENSE.txt',
            'rasterizer': 'resvg-py 0.5.0, longer side 384 px (the 142 icons of template 2.5.0) or 192 px (later icons)',
            'note': 'Eleven icons were fetched from the master branch before the pin (skills/format-resume/assets/devicon/'
                'sources.json); the others are in pinned-sources.json beside it, with the original SVGs, the variant '
                'and the PNG side. Logos remain trademarks of their owners.'},
        'names': dict(sorted(names.items())), 'icons': dict(sorted(icons.items()))}
    (TEMPLATE / 'technology-icons.json').write_text(json.dumps(pack, ensure_ascii=False, indent=1) + '\n')
    print('skipped:', ', '.join(skipped) or 'none')
    print('dropped altnames:', '; '.join(dropped) or 'none')
    print(len(icons), 'icons', len(names), 'names', (TEMPLATE / 'technology-icons.json').stat().st_size, 'bytes')


if __name__ == '__main__':
    {'fetch': fetch, 'build': build}[sys.argv[1]]()
