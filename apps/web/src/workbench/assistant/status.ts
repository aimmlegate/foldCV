import { terminal, type AssistantView } from "../../assistant/controller";
import { runText } from "../../assistant/presentation";

export function activityText(view: AssistantView, active: boolean): string {
  return active && terminal(view.run) && !view.pendingSend && !view.submitting
    ? "Подтверждаем изменения в редакторе" : runText(view);
}
