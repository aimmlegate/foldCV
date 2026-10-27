import { ProjectEditorConnection } from "../rich/v7-connection";
import { applicationTabActive } from "./tab";

/** Only the tab that holds the browser lock may take the project's editor token. */
export async function openEditor(project: string): Promise<ProjectEditorConnection> {
  if (!applicationTabActive()) throw new Error("TAB_LOCK_REQUIRED");
  const connection = await ProjectEditorConnection.open(project);
  if (!applicationTabActive()) throw new Error("TAB_LOCK_REQUIRED");
  return connection;
}
