from flask import Blueprint, jsonify, g

from server.auth import require_auth
from server.db_session import get_db
from server.events import event_broadcaster
from server.payload import read_payload
from server.tables import exclusive_partners, get_spec
from server.validation import checked_columns

records_bp = Blueprint("records", __name__)


@records_bp.route("/<table_name>/<int:row_id>", methods=["DELETE"])
@require_auth
def delete_record(table_name, row_id):
    spec = get_spec(table_name)
    if spec is None or not spec.row_editable:
        return jsonify({"error": "Unauthorized target table"}), 400

    conn = get_db()
    with conn:
        if spec.is_catalog:
            removed = conn.execute(
                f"DELETE FROM {table_name} WHERE id = ?", (row_id,)
            ).rowcount
        else:
            removed = conn.execute(
                f"DELETE FROM {table_name} WHERE id = ? AND user_id = ?", (row_id, g.user_id)
            ).rowcount

    if not removed:
        return jsonify({"error": f"No row {row_id} of {table_name} that this member may delete."}), 404

    if spec.is_catalog:
        event_broadcaster.broadcast(
            "catalog_updated", {"table": table_name, "action": "delete", "id": row_id}
        )
    return jsonify({"status": "success"})


@records_bp.route("/<table_name>/<int:row_id>", methods=["PATCH"])
@require_auth
def update_record(table_name, row_id):
    spec = get_spec(table_name)
    if spec is None or not spec.row_editable:
        return jsonify({"error": "Unauthorized target table"}), 400

    d = read_payload("col", "val")
    db_col = d.get("col")
    new_val = d.get("val")

    if db_col not in spec.mutable_columns:
        return jsonify(
            {"error": f"Column '{db_col}' is not permitted for modification on {table_name}"}
        ), 400

    conn = get_db()

    if db_col.endswith("_item_id"):
        if not isinstance(new_val, str):
            return jsonify(
                {"error": f"An item name must be text, not a {type(new_val).__name__}."}
            ), 400
        ref_tbl = db_col.replace("_item_id", "_items")
        res = conn.execute(
            f"SELECT id FROM {ref_tbl} WHERE name = ? COLLATE NOCASE", (new_val,)
        ).fetchone()
        if not res:
            return jsonify({"error": f"Item '{new_val}' not found in {ref_tbl} catalog."}), 400
        val = res["id"]
    else:
        val = checked_columns(conn, table_name, {db_col: new_val})[db_col]

    assignments = ", ".join(
        [f"{db_col} = ?"] + [f"{partner} = NULL"
                             for partner in sorted(exclusive_partners(table_name, db_col))])

    with conn:
        if spec.is_catalog:
            changed = conn.execute(
                f"UPDATE {table_name} SET {assignments} WHERE id = ?", (val, row_id)
            ).rowcount
        else:
            changed = conn.execute(
                f"UPDATE {table_name} SET {assignments} WHERE id = ? AND user_id = ?",
                (val, row_id, g.user_id),
            ).rowcount

    if not changed:
        return jsonify({"error": f"No row {row_id} of {table_name} that this member may edit."}), 404

    if spec.is_catalog:
        event_broadcaster.broadcast(
            "catalog_updated",
            {"table": table_name, "action": "update", "id": row_id, "col": db_col},
        )
    return jsonify({"status": "success"})
