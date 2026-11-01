import type { OrderDocument } from "../../rich/technology-order";
import type { WorkingFacts } from "../../contracts/generated/working_facts";
import { technologyKey } from "../../rich/panel-intents";

const groups = [
  { context: /frontend|front.end|фронтенд|интерфейс|верст|вёрст|web|веб|javascript|typescript|react|vue|angular/iu,
    names: "JavaScript|TypeScript|HTML|CSS|React|Next.js|Vue.js|Nuxt|Angular|Svelte|SvelteKit|Astro|SolidJS|jQuery|Redux|Redux Toolkit|Zustand|MobX|XState|TanStack Query|React Router|React Hook Form|Zod|Tailwind CSS|Sass|Less|CSS Modules|styled-components|Emotion|Bootstrap|Material UI|Ant Design|Radix UI|shadcn/ui|Vite|Webpack|Rollup|Parcel|Babel|ESLint|Prettier|Storybook|Web Components|PWA|WebAssembly|Accessibility|SEO" },
  { context: /backend|back.end|бэкенд|сервер|api|микросервис|microservice|java|python|golang|node|php|c#|\.net/iu,
    names: "Python|Java|C#|Go|Rust|C|C++|PHP|Ruby|Scala|Elixir|Erlang|Clojure|Haskell|F#|Lua|Perl|Node.js|Deno|Bun|Django|Flask|FastAPI|Starlette|aiohttp|Pydantic|SQLAlchemy|Alembic|Celery|Spring|Spring Boot|Spring Security|Hibernate|Maven|Gradle|Quarkus|Micronaut|Jakarta EE|.NET|ASP.NET Core|Entity Framework|Dapper|Express|NestJS|Fastify|Koa|Hono|Laravel|Symfony|Rails|Phoenix|Gin|Echo|Fiber|Actix|Axum|REST|GraphQL|gRPC|WebSocket|OpenAPI|Swagger|OAuth 2.0|OpenID Connect|JWT|Keycloak|Nginx|Apache HTTP Server|IIS|RabbitMQ|Apache Kafka|NATS|Redis|Memcached|Elasticsearch|OpenSearch" },
  { context: /data|данны|аналит|analyt|sql|database|баз[аыу]|warehouse|хранилищ|etl|bi\b/iu,
    names: "SQL|PostgreSQL|MySQL|MariaDB|SQLite|Microsoft SQL Server|Oracle Database|MongoDB|Cassandra|ClickHouse|DuckDB|BigQuery|Snowflake|Amazon Redshift|Amazon Athena|Amazon DynamoDB|Neo4j|Couchbase|CockroachDB|TimescaleDB|InfluxDB|Apache Druid|Apache Pinot|Trino|Presto|Apache Spark|PySpark|Apache Flink|Apache Hadoop|Apache Hive|Apache Iceberg|Delta Lake|dbt|Apache Airflow|Dagster|Prefect|Kafka Connect|Debezium|Fivetran|Airbyte|Pandas|NumPy|Polars|Dask|Jupyter|R|Julia|MATLAB|Power BI|Tableau|Looker|Looker Studio|Metabase|Apache Superset|Qlik Sense|Google Analytics|Яндекс Метрика|Excel|Power Query|VBA|DAX|ETL|A/B testing" },
  { context: /devops|sre|platform|платформ|инфраструкт|cloud|облак|linux|ci\/cd|kubernetes|k8s|docker|администр/iu,
    names: "Linux|Ubuntu|Debian|CentOS|Red Hat Enterprise Linux|Alpine Linux|Windows Server|Bash|PowerShell|Zsh|Docker|Docker Compose|Podman|Kubernetes|Helm|Kustomize|OpenShift|Nomad|containerd|Terraform|OpenTofu|Pulumi|Ansible|Puppet|Chef|SaltStack|Packer|Vagrant|Jenkins|GitHub Actions|GitLab CI/CD|CircleCI|TeamCity|Bamboo|Argo CD|Flux|AWS|Microsoft Azure|Google Cloud|Yandex Cloud|VK Cloud|DigitalOcean|Cloudflare|Amazon EC2|Amazon S3|AWS Lambda|Amazon ECS|Amazon EKS|Amazon RDS|Azure Functions|Azure DevOps|GKE|Cloud Run|Prometheus|Grafana|Datadog|New Relic|Zabbix|Nagios|VictoriaMetrics|Loki|Fluent Bit|Logstash|Kibana|Jaeger|OpenTelemetry|Sentry|Istio|Linkerd|Envoy|HAProxy|Traefik|Consul|Vault|etcd|MinIO|Ceph|Proxmox|VMware|Hyper-V|TCP/IP|DNS|HTTP|TLS|VPN|WireGuard" },
  { context: /mobile|мобиль|ios|android|swift|kotlin|flutter|react native/iu,
    names: "Kotlin|Swift|Objective-C|Dart|Flutter|React Native|Expo|Android SDK|Jetpack Compose|Android Jetpack|Coroutines|RxJava|Dagger|Hilt|Koin|Room|Retrofit|OkHttp|SwiftUI|UIKit|Combine|Core Data|Realm|RxSwift|Alamofire|CocoaPods|Swift Package Manager|Xcode|Android Studio|Firebase|Crashlytics|App Center|Fastlane|Kotlin Multiplatform|Ionic|Capacitor|.NET MAUI" },
  { context: /test|qa\b|тест|качеств|quality|автоматизац.*тест/iu,
    names: "Playwright|Cypress|Selenium|WebdriverIO|Puppeteer|Appium|Detox|Maestro|JUnit|TestNG|pytest|unittest|Jest|Vitest|Mocha|Chai|Testing Library|NUnit|xUnit|PHPUnit|RSpec|Cucumber|SpecFlow|Allure|TestRail|Qase|Zephyr|Postman|Insomnia|REST Assured|SoapUI|JMeter|k6|Gatling|Locust|Artillery|WireMock|MockServer|MSW|Testcontainers|Charles Proxy|Fiddler|BrowserStack|Sauce Labs|ReportPortal" },
  { context: /machine|learning|нейро|модел|ии\b|ai\b|ml\b|llm|nlp|vision|deep|искусствен/iu,
    names: "PyTorch|TensorFlow|Keras|scikit-learn|XGBoost|LightGBM|CatBoost|SciPy|Statsmodels|Hugging Face|Transformers|spaCy|NLTK|OpenCV|Pillow|ONNX|TensorRT|CUDA|cuDNN|JAX|Ray|MLflow|DVC|Kubeflow|BentoML|Weights & Biases|ClearML|LangChain|LangGraph|LlamaIndex|vLLM|Ollama|llama.cpp|OpenAI API|Azure OpenAI|Sentence Transformers|FAISS|Qdrant|Milvus|Weaviate|Pinecone|pgvector|Chroma|RAG|NLP|Computer Vision|Stable Diffusion" },
  { context: /security|безопас|защит|pentest|soc\b|siem|кибер/iu,
    names: "OWASP|Burp Suite|OWASP ZAP|Nmap|Wireshark|Metasploit|Kali Linux|Nessus|OpenVAS|Trivy|Snyk|SonarQube|Semgrep|Checkmarx|Fortify|HashiCorp Vault|Splunk|Wazuh|Suricata|Snort|YARA|Sigma|MITRE ATT&CK|SIEM|SOAR|EDR|DLP|PKI|WAF|SAML" },
  { context: /design|дизайн|ux|ui|прототип|макет|product|продукт|управлен|manager|scrum|agile/iu,
    names: "Figma|FigJam|Sketch|Adobe XD|Adobe Photoshop|Adobe Illustrator|Adobe After Effects|Adobe InDesign|Framer|Webflow|Tilda|Miro|Mural|Balsamiq|Axure RP|Zeplin|InVision|Principle|ProtoPie|Blender|Jira|Confluence|Notion|Linear|Trello|Asana|YouTrack|Azure Boards|ClickUp|Monday.com|MS Project|Productboard|Amplitude|Mixpanel|Hotjar|Dovetail|Maze|Useberry|Scrum|Kanban|BPMN|UML|C4 Model|PlantUML|Mermaid" },
  { context: /enterprise|erp|crm|1с|1c|sap|salesforce|бизнес|business|интеграц/iu,
    names: "1С:Предприятие|1С:Бухгалтерия|1С:ERP|1С:ЗУП|1С:Управление торговлей|1С-Битрикс|Битрикс24|SAP|SAP ABAP|SAP HANA|SAP S/4HANA|Salesforce|Apex|Microsoft Dynamics 365|ServiceNow|Odoo|Oracle E-Business Suite|Camunda|Apache Camel|MuleSoft|WSO2|BizTalk|RabbitMQ|ESB|SOAP|XML|XSLT|EDI|DocuSign|Directum|ELMA|Creatio" },
  { context: /game|игр|unity|unreal|embedded|встраива|iot|робот|robot|hardware|микроконтрол/iu,
    names: "Unity|Unreal Engine|Godot|Cocos2d|Phaser|Three.js|Babylon.js|OpenGL|Vulkan|DirectX|WebGPU|WebGL|HLSL|GLSL|SDL|SFML|CMake|Make|Ninja|Qt|QML|GTK|Electron|Tauri|JUCE|Arduino|ESP32|STM32|Raspberry Pi|FreeRTOS|Zephyr RTOS|Embedded Linux|Yocto|Buildroot|ROS|ROS 2|MQTT|Modbus|CAN|I2C|SPI|UART|Verilog|VHDL|FPGA|LabVIEW|Simulink" },
  { context: /./u, names: "Git|GitHub|GitLab|Bitbucket|SVN|Mercurial|VS Code|IntelliJ IDEA|PyCharm|Rider|WebStorm|Vim|Neovim|Emacs|npm|pnpm|Yarn|pip|Poetry|uv|Conda|NuGet|Composer|Cargo|JSON|YAML|Markdown|Regular expressions" },
] as const;

const aliases: Readonly<Record<string, readonly string[]>> = {
  JavaScript: ["js", "джаваскрипт"], TypeScript: ["ts", "тайпскрипт"], Python: ["питон"],
  "C#": ["csharp", "c sharp", "си шарп"], "C++": ["cpp", "си плюс плюс"], Go: ["golang"],
  "React": ["reactjs", "react.js"], "Vue.js": ["vue", "vuejs"], "Node.js": ["node", "nodejs"],
  "Next.js": ["next", "nextjs"], "PostgreSQL": ["postgres", "постгрес"], "Kubernetes": ["k8s"],
  ".NET": ["dotnet"], "Microsoft SQL Server": ["mssql", "ms sql"], "1С:Предприятие": ["1c", "1с"],
};
export const technologyCatalog = [...new Set(groups.flatMap(group => group.names.split("|")))];

function rawText(value: unknown): string {
  if (Array.isArray(value)) return value.map(rawText).join(" ");
  if (typeof value !== "object" || value === null) return "";
  if ("rawText" in value && typeof value.rawText === "string") return value.rawText;
  return Object.values(value).map(rawText).join(" ");
}

function description(document: OrderDocument | undefined, jobId: string | null): string {
  const text: string[] = [];
  const inline = (value: unknown): string => {
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map(inline).join(" ");
    if (typeof value !== "object" || value === null) return "";
    if ("text" in value && typeof value.text === "string") return value.text;
    return ["content", "rows", "cells"].map(key => key in value ? inline(Reflect.get(value, key)) : "").join(" ");
  };
  const visit = (block: OrderDocument["regions"][number]["blocks"][number], parent: string | null) => {
    const recordId: unknown = typeof block.props === "object" && block.props !== null ? Reflect.get(block.props, "recordId") : null;
    const owner = block.type === "section" ? (typeof recordId === "string" && recordId) || parent : parent;
    if (jobId === null || owner === jobId) text.push(inline(block.content));
    block.children.forEach(child => visit(child, owner));
  };
  document?.regions.forEach(region => region.blocks.forEach(block => visit(block, null)));
  return text.join(" ");
}

export function technologySuggestions(facts: WorkingFacts, jobId: string | null, query: string, document?: OrderDocument): string[] {
  const context = technologyKey(facts.records.filter(record => record.kind !== "technology" && (jobId === null || record.id === jobId || "jobId" in record && record.jobId === jobId))
    .map(rawText).join(" ") + " " + description(document, jobId));
  const existing = facts.records.filter(record => record.kind === "technology").map(record => record.display.rawText).filter(name => technologyKey(name));
  const catalog = [...new Map([...technologyCatalog, ...existing].map(name => [technologyKey(name), name])).values()];
  const relevant = new Set(groups.filter(group => group.context.test(context)).flatMap(group => group.names.split("|")));
  const tokens = technologyKey(query).split(/\s+/u).filter(Boolean);
  const mentioned = (name: string) => {
    const key = technologyKey(name);
    // An empty key is found at every position, so the search below would never move on.
    if (!key) return false;
    let start = context.indexOf(key);
    while (start >= 0) {
      if (!/[\p{L}\p{N}]/u.test(context[start - 1] ?? "") && !/[\p{L}\p{N}]/u.test(context[start + key.length] ?? "")) return true;
      start = context.indexOf(key, start + key.length);
    }
    return false;
  };
  const score = (name: string) => (mentioned(name) || (aliases[name] ?? []).some(mentioned) ? 100 : 0) + (relevant.has(name) ? 10 : 0);
  return catalog.filter(name => tokens.every(token => technologyKey([name, ...(aliases[name] ?? [])].join(" ")).includes(token)))
    .map(name => ({ name, score: score(name) })).sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, "ru", { sensitivity: "base" }))
    .map(item => item.name);
}
