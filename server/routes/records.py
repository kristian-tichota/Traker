from flask import Blueprint, g

from server.auth import require_auth
from server.db_session import get_db
from server.events import catalog_updated
from server.payload import BadValue, NotFound, read_payload
from server.tables import exclusive_partners, get_spec
from server.validation import checked_columns

records_bp = Blueprint("records", __name__)


def _editable(table_name):
    """Return the registration of a table editable by row, or the refusal."""
    spec = get_spec(table_name)
    if spec is None or not spec.row_editable:
        raise BadValue("Unauthorized target table")
    return spec


def _reachable(spec, row_id):
    """Return the WHERE clause and parameters matching a row this member may touch."""
    if spec.is_catalog:
        return "id = ?", (row_id,)
    return "id = ? AND user_id = ?", (row_id, g.user_id)


@records_bp.route("/<table_name>/<int:row_id>", methods=["DELETE"])
@require_auth
def delete_record(table_name, row_id):
    spec = _editable(table_name)
    where, params = _reachable(spec, row_id)
    conn = get_db()
    with conn:
        removed = conn.execute(f"DELETE FROM {table_name} WHERE {where}", params).rowcount

    if not removed:
        raise NotFound(f"No row {row_id} of {table_name} that this member may delete.")

    if spec.is_catalog:
        catalog_updated(table=table_name, action="delete", id=row_id)
    return {"status": "success"}


@records_bp.route("/<table_name>/<int:row_id>", methods=["PATCH"])
@require_auth
def update_record(table_name, row_id):
    spec = _editable(table_name)
    d = read_payload("col", "val")
    db_col, new_val = d["col"], d["val"]

    if not isinstance(db_col, str) or db_col not in spec.mutable_columns:
        raise BadValue(f"Column '{db_col}' is not permitted for modification on {table_name}")

    conn = get_db()

    if db_col.endswith("_item_id"):
        if not isinstance(new_val, str):
            raise BadValue(f"An item name must be text, not a {type(new_val).__name__}.")
        ref_tbl = db_col.replace("_item_id", "_items")
        res = conn.execute(
            f"SELECT id FROM {ref_tbl} WHERE name = ? COLLATE NOCASE", (new_val,)
        ).fetchone()
        if not res:
            raise BadValue(f"Item '{new_val}' not found in {ref_tbl} catalog.")
        val = res["id"]
    else:
        val = checked_columns(conn, table_name, {db_col: new_val})[db_col]

    assignments = ", ".join(
        [f"{db_col} = ?"] + [f"{partner} = NULL"
                             for partner in sorted(exclusive_partners(table_name, db_col))])
    where, params = _reachable(spec, row_id)
    with conn:
        changed = conn.execute(
            f"UPDATE {table_name} SET {assignments} WHERE {where}", (val, *params)
        ).rowcount

    if not changed:
        raise NotFound(f"No row {row_id} of {table_name} that this member may edit.")

    if spec.is_catalog:
        catalog_updated(table=table_name, action="update", id=row_id, col=db_col)
    return {"status": "success"}
