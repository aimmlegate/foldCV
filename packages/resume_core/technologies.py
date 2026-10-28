"""Versioned literal technology catalog and conservative name resolution."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


CATALOG_VERSION = "foldcv-3"


@dataclass(frozen=True)
class CatalogEntry:
    canonical_id: str
    category: str
    logo: str | None
    aliases: tuple[str, ...]


CATALOG = (
    CatalogEntry('golang', 'language', '@library/golang.png', ('golang', 'go (golang)')),
    CatalogEntry('python', 'language', '@library/python.png', ('python',)),
    CatalogEntry('csharp', 'language', '@library/csharp.png', ('c#', 'csharp', 'c sharp')),
    CatalogEntry('cplusplus', 'language', '@library/cplusplus.png', ('c++',)),
    CatalogEntry('dotnet', 'framework', '@library/dotnet.png', ('.net', '.net core', '.net framework', '.net standard')),
    CatalogEntry('postgresql', 'database', '@library/postgresql.png', ('postgresql', 'postgres', 'postges', 'postrgesql')),
    CatalogEntry('redis', 'database', '@library/redis.png', ('redis',)),
    CatalogEntry('kafka', 'messaging', '@library/kafka.png', ('kafka', 'apache kafka')),
    CatalogEntry('rabbitmq', 'messaging', '@library/rabbitmq.png', ('rabbitmq',)),
    CatalogEntry('kubernetes', 'platform', '@library/kubernetes.png', ('kubernetes', 'k8s')),
    CatalogEntry('docker', 'platform', '@library/docker.png', ('docker',)),
    CatalogEntry('php', 'language', '@library/php.png', ('php',)),
    CatalogEntry('nodejs', 'runtime', '@library/nodejs.png', ('node.js', 'nodejs')),
    CatalogEntry('grpc', 'framework', '@library/grpc.png', ('grpc',)),
    CatalogEntry('linux', 'platform', '@library/linux.png', ('linux',)),
    CatalogEntry('fastapi', 'framework', '@library/fastapi.png', ('fastapi',)),
    CatalogEntry('djangorest', 'framework', '@library/djangorest.png', ('django rest framework', 'django rest framework (drf)')),
    CatalogEntry('grafana', 'observability', '@library/grafana.png', ('grafana',)),
    CatalogEntry('kibana', 'observability', '@library/kibana.png', ('kibana',)),
    CatalogEntry('git', 'tool', '@library/git.png', ('git',)),
    CatalogEntry('ansible', 'automation', '@library/ansible.png', ('ansible',)),
    CatalogEntry('terraform', 'automation', '@library/terraform.png', ('terraform',)),
    CatalogEntry('jenkins', 'automation', '@library/jenkins.png', ('jenkins',)),
    CatalogEntry('javascript', 'language', '@library/javascript.png', ('javascript', 'js', 'ecmascript')),
    CatalogEntry('typescript', 'language', '@library/typescript.png', ('typescript', 'ts')),
    CatalogEntry('java', 'language', '@library/java.png', ('java',)),
    CatalogEntry('rust', 'language', '@library/rust.png', ('rust',)),
    CatalogEntry('c', 'language', '@library/c.png', ('c',)),
    CatalogEntry('mysql', 'database', '@library/mysql.png', ('mysql',)),
    CatalogEntry('mariadb', 'database', '@library/mariadb.png', ('mariadb',)),
    CatalogEntry('mongodb', 'database', '@library/mongodb.png', ('mongodb', 'mongo db')),
    CatalogEntry('elasticsearch', 'database', '@library/elasticsearch.png', ('elasticsearch', 'elastic search')),
    CatalogEntry('sqlite', 'database', '@library/sqlite.png', ('sqlite',)),
    CatalogEntry('oracle', 'database', '@library/oracle.png', ('oracle', 'oracle database')),
    CatalogEntry('mssql', 'database', '@library/mssql.png', ('sql server', 'mssql', 'ms sql', 'microsoft sql server')),
    CatalogEntry('clickhouse', 'database', '@library/clickhouse.png', ('clickhouse',)),
    CatalogEntry('cassandra', 'database', '@library/cassandra.png', ('cassandra', 'apache cassandra')),
    CatalogEntry('prometheus', 'observability', '@library/prometheus.png', ('prometheus',)),
    CatalogEntry('zabbix', 'observability', '@library/zabbix.png', ('zabbix',)),
    CatalogEntry('logstash', 'observability', '@library/logstash.png', ('logstash',)),
    CatalogEntry('opensearch', 'observability', '@library/opensearch.png', ('opensearch',)),
    CatalogEntry('nginx', 'server', '@library/nginx.png', ('nginx',)),
    CatalogEntry('apache', 'server', '@library/apache.png', ('apache', 'apache http server', 'apache2')),
    CatalogEntry('bash', 'language', '@library/bash.png', ('bash', 'shell', 'shell scripting')),
    CatalogEntry('powershell', 'language', '@library/powershell.png', ('powershell',)),
    CatalogEntry('gitlab', 'tool', '@library/gitlab.png', ('gitlab', 'gitlab ci', 'gitlab ci/cd', 'gitlab-ci')),
    CatalogEntry('github', 'tool', '@library/github.png', ('github', 'github actions')),
    CatalogEntry('aws', 'platform', '@library/aws.png', ('aws', 'amazon web services')),
    CatalogEntry('azure', 'platform', '@library/azure.png', ('azure', 'microsoft azure')),
    CatalogEntry('gcp', 'platform', '@library/gcp.png', ('gcp', 'google cloud', 'google cloud platform')),
    CatalogEntry('react', 'framework', '@library/react.png', ('react', 'react.js', 'reactjs')),
    CatalogEntry('vue', 'framework', '@library/vue.png', ('vue', 'vue.js', 'vuejs')),
    CatalogEntry('angular', 'framework', '@library/angular.png', ('angular',)),
    CatalogEntry('django', 'framework', '@library/django.png', ('django',)),
    CatalogEntry('flask', 'framework', '@library/flask.png', ('flask',)),
    CatalogEntry('spring', 'framework', '@library/spring.png', ('spring', 'spring boot')),
    CatalogEntry('swift', 'language', '@library/swift.png', ('swift',)),
    CatalogEntry('kotlin', 'language', '@library/kotlin.png', ('kotlin',)),
    CatalogEntry('ruby', 'language', '@library/ruby.png', ('ruby',)),
    CatalogEntry('rails', 'framework', '@library/rails.png', ('rails', 'ruby on rails')),
    CatalogEntry('windows', 'platform', '@library/windows.png', ('windows', 'windows server')),
    CatalogEntry('vault', 'security', '@library/vault.png', ('vault', 'hashicorp vault')),
    CatalogEntry('ubuntu', 'platform', '@library/ubuntu.png', ('ubuntu',)),
    CatalogEntry('debian', 'platform', '@library/debian.png', ('debian',)),
    CatalogEntry('centos', 'platform', '@library/centos.png', ('centos',)),
    CatalogEntry('rhel', 'platform', '@library/rhel.png', ('rhel', 'red hat', 'red hat enterprise linux')),
    CatalogEntry('helm', 'automation', '@library/helm.png', ('helm',)),
    CatalogEntry('argocd', 'automation', '@library/argocd.png', ('argocd', 'argo cd')),
    CatalogEntry('sql', 'language', '@library/sql.png', ('sql',)),
    CatalogEntry('html', 'language', '@library/html.png', ('html', 'html5')),
    CatalogEntry('css', 'language', '@library/css.png', ('css', 'css3')),
    CatalogEntry('http', 'protocol', '@library/http.png', ('http', 'https', 'http/https')),
    CatalogEntry('tcpip', 'protocol', '@library/tcpip.png', ('tcp/ip', 'tcp', 'ip')),
    CatalogEntry('dns', 'protocol', '@library/dns.png', ('dns',)),
    CatalogEntry('rest', 'protocol', '@library/rest.png', ('rest', 'rest api', 'restful', 'restful api')),
    CatalogEntry('graphql', 'protocol', '@library/graphql.png', ('graphql',)),
    CatalogEntry('openapi', 'tool', '@library/openapi.png', ('openapi', 'swagger')),
    CatalogEntry('oauth', 'protocol', '@library/oauth.png', ('oauth', 'oauth2', 'oauth 2.0')),
    CatalogEntry('ldap', 'protocol', '@library/ldap.png', ('ldap', 'openldap')),
    CatalogEntry('vmware', 'platform', '@library/vmware.png', ('vmware', 'vsphere', 'vmware vsphere')),
    CatalogEntry('proxmox', 'platform', '@library/proxmox.png', ('proxmox', 'proxmox ve')),
    CatalogEntry('kvm', 'platform', '@library/kvm.png', ('kvm',)),
    CatalogEntry('vagrant', 'automation', '@library/vagrant.png', ('vagrant',)),
    CatalogEntry('puppet', 'automation', '@library/puppet.png', ('puppet',)),
    CatalogEntry('saltstack', 'automation', '@library/saltstack.png', ('saltstack', 'salt stack')),
    CatalogEntry('haproxy', 'server', '@library/haproxy.png', ('haproxy',)),
    CatalogEntry('consul', 'automation', '@library/consul.png', ('consul',)),
    CatalogEntry('etcd', 'database', '@library/etcd.png', ('etcd',)),
    CatalogEntry('minio', 'database', '@library/minio.png', ('minio',)),
    CatalogEntry('ceph', 'database', '@library/ceph.png', ('ceph',)),
    CatalogEntry('s3', 'protocol', '@library/s3.png', ('s3', 'amazon s3')),
    CatalogEntry('openstack', 'platform', '@library/openstack.png', ('openstack',)),
    CatalogEntry('openshift', 'platform', '@library/openshift.png', ('openshift',)),
    CatalogEntry('istio', 'platform', '@library/istio.png', ('istio',)),
    CatalogEntry('envoy', 'server', '@library/envoy.png', ('envoy',)),
    CatalogEntry('fluentd', 'observability', '@library/fluentd.png', ('fluentd',)),
    CatalogEntry('fluentbit', 'observability', '@library/fluentbit.png', ('fluent bit', 'fluentbit')),
    CatalogEntry('victoriametrics', 'observability', '@library/victoriametrics.png', ('victoriametrics',)),
    CatalogEntry('loki', 'observability', '@library/loki.png', ('loki', 'grafana loki')),
    CatalogEntry('jaeger', 'observability', '@library/jaeger.png', ('jaeger',)),
    CatalogEntry('opentelemetry', 'observability', '@library/opentelemetry.png', ('opentelemetry', 'otel')),
    CatalogEntry('teamcity', 'automation', '@library/teamcity.png', ('teamcity',)),
    CatalogEntry('bamboo', 'automation', '@library/bamboo.png', ('bamboo',)),
    CatalogEntry('maven', 'tool', '@library/maven.png', ('maven',)),
    CatalogEntry('gradle', 'tool', '@library/gradle.png', ('gradle',)),
    CatalogEntry('npm', 'tool', '@library/npm.png', ('npm',)),
    CatalogEntry('yarn', 'tool', '@library/yarn.png', ('yarn',)),
    CatalogEntry('webpack', 'tool', '@library/webpack.png', ('webpack',)),
    CatalogEntry('vite', 'tool', '@library/vite.png', ('vite',)),
    CatalogEntry('pandas', 'framework', '@library/pandas.png', ('pandas',)),
    CatalogEntry('numpy', 'framework', '@library/numpy.png', ('numpy',)),
    CatalogEntry('pytorch', 'framework', '@library/pytorch.png', ('pytorch',)),
    CatalogEntry('tensorflow', 'framework', '@library/tensorflow.png', ('tensorflow',)),
    CatalogEntry('spark', 'platform', '@library/spark.png', ('spark', 'apache spark')),
    CatalogEntry('hadoop', 'platform', '@library/hadoop.png', ('hadoop', 'apache hadoop')),
    CatalogEntry('airflow', 'automation', '@library/airflow.png', ('airflow', 'apache airflow')),
    CatalogEntry('celery', 'framework', '@library/celery.png', ('celery',)),
    CatalogEntry('aiohttp', 'framework', '@library/aiohttp.png', ('aiohttp',)),
    CatalogEntry('asyncio', 'framework', '@library/asyncio.png', ('asyncio',)),
    CatalogEntry('sqlalchemy', 'framework', '@library/sqlalchemy.png', ('sqlalchemy',)),
    CatalogEntry('laravel', 'framework', '@library/laravel.png', ('laravel',)),
    CatalogEntry('symfony', 'framework', '@library/symfony.png', ('symfony',)),
    CatalogEntry('yii', 'framework', '@library/yii.png', ('yii', 'yii2')),
    CatalogEntry('qt', 'framework', '@library/qt.png', ('qt',)),
    CatalogEntry('boost', 'framework', '@library/boost.png', ('boost',)),
    CatalogEntry('stl', 'framework', '@library/stl.png', ('stl',)),
    CatalogEntry('wpf', 'framework', '@library/wpf.png', ('wpf',)),
    CatalogEntry('aspnet', 'framework', '@library/aspnet.png', ('asp.net', 'asp.net core')),
    CatalogEntry('entityframework', 'framework', '@library/entityframework.png', ('entity framework', 'ef core')),
    CatalogEntry('unity', 'platform', '@library/unity.png', ('unity', 'unity3d')),
    CatalogEntry('unreal', 'platform', '@library/unreal.png', ('unreal engine', 'ue4', 'ue5')),
    CatalogEntry('selenium', 'tool', '@library/selenium.png', ('selenium',)),
    CatalogEntry('pytest', 'tool', '@library/pytest.png', ('pytest',)),
    CatalogEntry('unittest', 'tool', '@library/unittest.png', ('unittest',)),
    CatalogEntry('junit', 'tool', '@library/junit.png', ('junit',)),
    CatalogEntry('jest', 'tool', '@library/jest.png', ('jest',)),
    CatalogEntry('playwright', 'tool', '@library/playwright.png', ('playwright',)),
    CatalogEntry('cypress', 'tool', '@library/cypress.png', ('cypress',)),
    CatalogEntry('postman', 'tool', '@library/postman.png', ('postman',)),
    CatalogEntry('jmeter', 'tool', '@library/jmeter.png', ('jmeter',)),
    CatalogEntry('locust', 'tool', '@library/locust.png', ('locust',)),
    CatalogEntry('jooq', 'framework', '@library/jooq.png', ('jooq',)),
    CatalogEntry('hibernate', 'framework', '@library/hibernate.png', ('hibernate',)),
)
BY_ID = {entry.canonical_id: entry for entry in CATALOG}
_ALIASES = {alias: entry.canonical_id for entry in CATALOG for alias in entry.aliases}
_VERSION = re.compile(r"\s+(?:v)?(\d+(?:\.\d+)*(?:[-+][a-z0-9.]+)?)$", re.I)


@dataclass(frozen=True)
class ResolvedTechnology:
    canonical_id: str | None
    display: str
    version: str | None
    status: str  # catalog, ambiguous, or unknown


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def split_version(display: str) -> tuple[str, str | None]:
    """The normalized name without a leading "microsoft " and a trailing version, and that version."""
    name = normalize_name(display)
    if name.startswith("microsoft "):
        name = name[len("microsoft "):]
    match = _VERSION.search(name)
    return (name[:match.start()], match.group(1)) if match else (name, None)


def resolve_technology(display: str) -> ResolvedTechnology:
    if not normalize_name(display):
        return ResolvedTechnology(None, display, None, "unknown")
    base, version = split_version(display)
    if base == "go" and version:
        base = "golang"
    if base in {"go", "drf", "r", "node"}:
        return ResolvedTechnology(None, display, version, "ambiguous")
    canonical_id = _ALIASES.get(base)
    return ResolvedTechnology(canonical_id, display, version,
                              "catalog" if canonical_id else "unknown")


def canonical_id(display: str) -> str | None:
    return resolve_technology(display).canonical_id


def technology_identity(record):
    """Use current catalog aliases even for saved records from an older catalog."""
    canonical = record.canonical_id.value or resolve_technology(record.display.raw_text).canonical_id
    return canonical or normalize_name(record.display.raw_text)


def is_technical(record):
    if isinstance(record, dict):
        explicit = record.get("technical")
        canonical = record["canonicalId"]["value"] or resolve_technology(record["display"]["rawText"]).canonical_id
    else:
        explicit, canonical = record.technical, technology_identity(record)
    return explicit if explicit is not None else canonical in BY_ID


def logo_path(entry):
    return "assets/technology-library/" + entry.logo.removeprefix("@library/") if entry.logo and entry.logo.startswith("@library/") else "skills/format-resume/assets/" + entry.logo if entry.logo else None
