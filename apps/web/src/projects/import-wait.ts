/** The default Settings import window, plus the cleanup, publication and outcome grace.
 * A longer Settings value is enforced by the server task; this cap is not raised above that default. */
export const IMPORT_WAIT_MS = (60 * 60 + 5 + 158 + 60) * 1000;
