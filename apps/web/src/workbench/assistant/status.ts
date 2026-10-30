import { terminal, type AssistantView } from "../../assistant/controller";
import { runText } from "../../assistant/presentation";

export function activityText(view: AssistantView, active: boolean): string {
  return active && terminal(view.run) && !view.pendingSend && !view.submitting
    ? view.proposalAction === "discard" ? "Отклоняем правки" : "Применяем правки" : runText(view);
}
