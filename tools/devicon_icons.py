"""Fetch pinned Devicon SVGs, render their PNGs and write the icon pack of the bundled template.

  .venv/bin/python -I tools/devicon_icons.py fetch   # network: downloads missing SVGs at REVISION
  .venv/bin/python -I tools/devicon_icons.py build   # offline: PNGs, pinned-sources.json and technology-icons.json

PNGs are rendered like the first eleven icons: resvg-py 0.5.0, the longer side 384 px, original colors.
devicon/sources.json keeps only those eleven: the frozen foldcv-reference manifest pins its bytes. The template gets one
pack asset, since a portable archive holds at most 47 entries and each captured asset is one of them.
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
RAW = 'https://raw.githubusercontent.com/devicons/devicon/' + REVISION + '/icons/'
SIDE = 384

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
    ('flutter', 'flutter', 'original', []), ('jquery', 'jquery', 'original', []), ('redux', 'redux', 'original', []),
    ('svelte', 'svelte', 'original', []), ('bootstrap', 'bootstrap', 'original', []),
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
# The catalog keys of template revision 2.4.0, kept so a name matched before still matches.
EARLIER_KEYS = {'python': 'python', 'c#': 'csharp', '.net': 'dotnet', '.net framework': 'dotnet',
    '.net и .net framework': 'dotnet', 'docker': 'docker', 'fastapi': 'fastapi', 'django rest framework': 'djangorest',
    'django rest framework (drf)': 'djangorest', 'grafana': 'grafana', 'kibana': 'kibana', 'c++': 'cplusplus',
    'grpc': 'grpc', 'linux': 'linux'}


def url(name, variant):
    return f'{RAW}{name}/{name}-{variant}.svg'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def fetch():
    import ssl
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())
    for identifier, name, variant, _names in ICONS:
        target = DEVICON / (identifier + '.svg')
        if target.exists():
            continue
        with urllib.request.urlopen(url(name, variant), timeout=30, context=context) as reply:
            raw = reply.read()
        if not raw.lstrip().startswith((b'<svg', b'<?xml')):
            raise ValueError('not an SVG: ' + name)
        target.write_bytes(raw)
        print('fetched', identifier, len(raw))


def render(raw):
    import resvg_py
    from PIL import Image
    from io import BytesIO
    text = raw.decode('utf-8')
    png = bytes(resvg_py.svg_to_bytes(svg_string=text, width=SIDE))
    with Image.open(BytesIO(png)) as image:
        if image.height > SIDE:
            png = bytes(resvg_py.svg_to_bytes(svg_string=text, height=SIDE))
    return png


def build():
    frozen = json.loads((DEVICON / 'sources.json').read_text())
    pinned, icons, names = {}, {}, dict(EARLIER_KEYS)
    for identifier, name, variant, extra in ICONS:
        svg = (DEVICON / (identifier + '.svg')).read_bytes()
        if b'<text' in svg or b'<image' in svg:
            raise ValueError('icon needs fonts or external images: ' + identifier)
        source = frozen.get(identifier)
        if source is None:
            png = render(svg)
            (DEVICON / (identifier + '.png')).write_bytes(png)
            source = pinned[identifier] = {'url': url(name, variant), 'revision': REVISION, 'release': RELEASE,
                'license': 'MIT', 'sha256': sha256(svg), 'pngSha256': sha256(png), 'rasterizer': 'resvg-py 0.5.0'}
        elif source['sha256'] != sha256(svg):
            raise ValueError('existing SVG differs from its recorded hash: ' + identifier)
        png = (DEVICON / (identifier + '.png')).read_bytes()
        icons[identifier] = {'source': source['url'], 'svgSha256': source['sha256'], 'sha256': sha256(png),
            'png': base64.b64encode(png).decode('ascii')}
        for key in [identifier, *extra]:
            if names.setdefault(key, identifier) != identifier:
                raise ValueError('one name binds two icons: ' + key)
    (DEVICON / 'pinned-sources.json').write_text(json.dumps(pinned, indent=2) + '\n')
    (TEMPLATE / 'devicon-LICENSE.txt').write_bytes((DEVICON / 'LICENSE').read_bytes())
    pack = {'schema': 'foldcv-icon-pack-1',
        'provenance': {'upstream': REPOSITORY, 'release': RELEASE, 'commit': REVISION, 'license': 'MIT',
            'licenseFile': 'devicon-LICENSE.txt', 'rasterizer': 'resvg-py 0.5.0, longer side 384 px',
            'note': 'Eleven icons were fetched from the master branch before the pin (skills/format-resume/assets/devicon/'
                'sources.json); the others are in pinned-sources.json beside it, with the original SVGs. Logos remain '
                'trademarks of their owners.'},
        'names': dict(sorted(names.items())), 'icons': dict(sorted(icons.items()))}
    (TEMPLATE / 'technology-icons.json').write_text(json.dumps(pack, ensure_ascii=False, indent=1) + '\n')
    print(len(icons), 'icons', (TEMPLATE / 'technology-icons.json').stat().st_size, 'bytes')


if __name__ == '__main__':
    {'fetch': fetch, 'build': build}[sys.argv[1]]()
