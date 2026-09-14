import logging

from flask import Blueprint, jsonify
from server.auth import require_auth
from server.db_session import get_db
from server.events import event_broadcaster
from server.payload import BadValue, read_payload
from server import sets as item_sets
from server.tables import CATALOG_DOMAINS, NAMED_CATALOG_TABLES
from server.validation import checked_columns, require_known_columns

log = logging.getLogger(__name__)

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.route("/<domain>", methods=["GET"])
@require_auth
def get_catalog(domain):
    table = CATALOG_DOMAINS.get(domain)
    if not table:
        return jsonify({"error": "Invalid domain"}), 400
    conn = get_db()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return jsonify([dict(r) for r in rows])


@catalog_bp.route("/<domain>", methods=["POST"])
@require_auth
def add_catalog_item(domain):
    table = CATALOG_DOMAINS.get(domain)
    if not table:
        return jsonify({"error": "Invalid domain"}), 400

    data = read_payload("name")

    conn = get_db()
    require_known_columns(table, data)
    values = checked_columns(conn, table, data)

    col_names = ", ".join(values)
    placeholders = ", ".join(f":{col}" for col in values)

    with conn:
        conn.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values)
    event_broadcaster.broadcast("catalog_updated", {"domain": domain, "table": table, "action": "insert"})
    return jsonify({"status": "success"})


@catalog_bp.route("/items/<path:name>", methods=["DELETE"])
@require_auth
def delete_item_by_name(name):
    conn = get_db()

    holding = item_sets.every_set_using(conn, name)
    if holding:
        parts = [
            f"{len(using)} {spec.word if len(using) == 1 else spec.word + 's'} "
            f"({', '.join(using)})"
            for spec, using in holding
        ]
        return jsonify({"error": (
            f"'{name}' is used by {' and '.join(parts)}. "
            f"Remove it from those first."
        )}), 409

    removed = 0
    with conn:
        for tbl in sorted(NAMED_CATALOG_TABLES):
            removed += conn.execute(
                f"DELETE FROM {tbl} WHERE name = ? COLLATE NOCASE", (name,)
            ).rowcount

    if not removed:
        return jsonify({"error": f"No catalog item named '{name}'."}), 404

    event_broadcaster.broadcast("catalog_updated", {"action": "delete", "name": name})
    return jsonify({"status": "success", "removed": removed})


def _set_domain(domain):
    """This domain's set registration, or the refusal that it has none."""
    spec = item_sets.spec_for(domain)
    if spec is None:
        raise BadValue(f"'{domain}' has no named sets.")
    return spec


@catalog_bp.route("/sets/<domain>", methods=["GET"])
@require_auth
def get_sets(domain):
    spec = _set_domain(domain)
    return jsonify([list(r) for r in item_sets.listing(get_db(), spec)])


def _component_amounts(conn, spec, entry, item_name):
    """One component's amount columns, coerced and checked."""
    given = {column: entry.get(column) for column in spec.amount_columns
             if entry.get(column) is not None}
    if spec.has_single_amount and "amount" not in given:
        raise BadValue(f"{item_name} needs an amount in {spec.unit}.")
    try:
        values = checked_columns(conn, spec.components_table, given)
    except BadValue as bad_amount:
        raise BadValue(f"{item_name}: {bad_amount}") from None
    if spec.has_single_amount and (values["amount"] is None or values["amount"] <= 0):
        raise BadValue(
            f"{item_name} needs an amount in {spec.unit} greater than zero.")
    return values


@catalog_bp.route("/sets/<domain>", methods=["POST"])
@require_auth
def add_set(domain):
    """Define a named set of catalog items."""
    spec = _set_domain(domain)

    data = read_payload("name", "components")
    name = data["name"]
    components = data["components"]

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": f"A {spec.word} needs a name."}), 400
    name = name.strip()
    if not isinstance(components, list) or not components:
        return jsonify({"error": f"'{name}' needs at least one component."}), 400

    conn = get_db()

    clash = conn.execute(
        f"SELECT name FROM {spec.catalog_table} WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if clash:
        return jsonify({"error": (
            f"'{clash['name']}' is already a {spec.domain} item. A {spec.word} needs "
            f"a name of its own, or logging it would be ambiguous."
        )}), 400

    existing = item_sets.find(conn, spec.domain, name)
    if existing:
        return jsonify({"error": (
            f"A {spec.word} called '{existing['name']}' already exists. "
            f"Remove it first, or give this one another name."
        )}), 400

    resolved = []
    for entry in components:
        if not isinstance(entry, dict):
            return jsonify({"error": (
                f"Each component is a {spec.domain} item name and its amount."
            )}), 400
        item_name = entry.get("item_name")
        if not isinstance(item_name, str) or not item_name.strip():
            return jsonify({"error": f"Each component needs a {spec.domain} name."}), 400
        row = conn.execute(
            f"SELECT id, name FROM {spec.catalog_table} WHERE name = ? COLLATE NOCASE",
            (item_name.strip(),)
        ).fetchone()
        if row is None:
            return jsonify({
                "error": f"{spec.domain.capitalize()} '{item_name}' not found in catalog."
            }), 400
        amounts = _component_amounts(conn, spec, entry, row["name"])
        resolved.append((row["id"], row["name"], amounts))

    named_twice = [n for _id, n, _a in resolved
                   if sum(1 for _i, other, _x in resolved if other == n) > 1]
    if named_twice:
        return jsonify({"error": (
            f"'{named_twice[0]}' is listed twice. Give one amount per component."
        )}), 400

    columns = ["set_id", spec.item_column, *spec.amount_columns]
    placeholders = ", ".join("?" * len(columns))
    with conn:
        cursor = conn.execute(
            "INSERT INTO item_sets (domain, name) VALUES (?, ?)", (spec.domain, name))
        conn.executemany(
            f"INSERT INTO {spec.components_table} ({', '.join(columns)}) "
            f"VALUES ({placeholders})",
            [(cursor.lastrowid, item_id,
              *(amounts.get(column, 0) for column in spec.amount_columns))
             for item_id, _n, amounts in resolved])

    event_broadcaster.broadcast(
        "catalog_updated",
        {"table": "item_sets", "action": "insert", "domain": spec.domain, "name": name})
    return jsonify({"status": "success", "components": len(resolved)})
