import { useState } from "react";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";

export function TableDialog({ close, apply }: { close: () => void; apply: (rows: number, columns: number) => void }) {
  const [rows, setRows] = useState(3), [columns, setColumns] = useState(2);
  const valid = Number.isInteger(rows) && rows >= 1 && rows <= 10 && Number.isInteger(columns) && columns >= 1 && columns <= 5;
  return <Dialog open close={close} title="Таблица"><form onSubmit={event => { event.preventDefault(); if (valid) apply(rows, columns); }}>
    <div className="fact-form-grid"><div><label htmlFor="uir-table-rows">Строк</label><input id="uir-table-rows" type="number" value={rows} min={1} max={10} required onChange={event => setRows(Number(event.currentTarget.value))} /></div>
      <div><label htmlFor="uir-table-columns">Столбцов</label><input id="uir-table-columns" type="number" value={columns} min={1} max={5} required onChange={event => setColumns(Number(event.currentTarget.value))} /></div></div>
    <div className="dialog-actions"><Button variant="quiet" onClick={close}>Отмена</Button><Button type="submit" variant="primary" disabled={!valid}>Вставить таблицу</Button></div>
  </form></Dialog>;
}
