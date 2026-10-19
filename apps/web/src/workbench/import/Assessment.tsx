import type { RichProjectResponse } from "../../contracts/generated/rich_project_response";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";

export function Assessment({ response, open, back }: { response: RichProjectResponse; open: () => void; back: () => void }) {
  const records = response.workspace.project?.facts.records ?? [];
  const warnings = response.workspace.warnings;
  const uncertain = warnings.some(item => ["source_not_resume", "source_resume_uncertain"].includes(item.code));
  const groups = [{ kind: "candidate", label: "Кандидат" }, { kind: "employment", label: "Места работы" }, { kind: "technology", label: "Технологии" },
    { kind: "education", label: "Образование" }, { kind: "language", label: "Языки" }];
  return <section className="check-screen" aria-label="Первичная проверка"><div className="check-content"><h2>Результат проверки</h2>
    <div className="check-result"><Icon name={uncertain ? "info" : "check"} /><div><strong>{uncertain ? "Проверьте выбранный источник" : "Текст похож на резюме"}</strong></div></div>
    <div className="check-tags">{groups.map(group => { const count = records.filter(record => record.kind === group.kind).length;
      return count > 0 && <span key={group.kind}>{group.label}: {count}</span>; })}</div>
    <div className="check-actions"><Button variant="primary" onClick={open}>{uncertain ? "Всё равно продолжить" : "Открыть редактор"}<Icon name="arrow" /></Button>
      <button className="text-button" onClick={back}>Вернуться к исходнику</button></div>
  </div></section>;
}
