export type Actionid = string;
export type Replacementid = string | null;
export type Reservationid = string;
export type Revision = number;
export type Sessionid = string;

export interface ImageUploadCapture {
  actionId: Actionid;
  replacementId?: Replacementid;
  reservationId: Reservationid;
  revision: Revision;
  sessionId: Sessionid;
}
