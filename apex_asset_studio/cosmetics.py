"""Resolve names and model packages from typed itemflav data, with evidence."""
from __future__ import annotations
import json
import re
from pathlib import Path
from .rpak.guid import guid_text


def rebuild_cosmetics(db):
    db.execute("DELETE FROM cosmetics")
    rows = db.execute("""SELECT a.id,a.guid,a.type,c.path,c.patch_count,d.name,d.status,d.details
        FROM assets a JOIN containers c ON c.id=a.container_id
        JOIN asset_details d ON d.asset_id=a.id WHERE c.status='ok' AND d.status IN
        ('settings_decoded','localization_decoded','on_demand_asset_decoded','on_demand_package_decoded')""").fetchall()
    groups = {}
    for row in rows:
        path = Path(row['path'])
        match = re.search(r'\((\d+)\)$',path.stem)
        generation = int(match.group(1)) if match else 0
        chain = (path.parent,re.sub(r'\(\d+\)$','',path.stem))
        entries = groups.setdefault(row['guid'],{})
        if chain not in entries or generation > entries[chain][0]:
            entries[chain] = (generation,dict(row))
    by_guid = {}
    for guid,chains in groups.items():
        candidates = [entry[1] for entry in chains.values()]
        if len({r['details'] for r in candidates}) == 1:
            by_guid[guid] = candidates[0]
    localizations = [json.loads(row["details"]) for row in by_guid.values()
                     if row["status"] == "localization_decoded" and json.loads(row["details"]).get("name") == "localization_english"]
    loc = localizations[0]["entries"] if len(localizations) == 1 else {}
    def localize(values):
        key = values.get("localizationKey_NAME", "")
        if not key:
            return values.get("skinName") or None, key
        return loc.get(guid_text(key.lstrip("#"))), key
    base = by_guid.get(guid_text("settings/base_itemflavors.rpak"))
    if not base:
        return 0
    base_values = json.loads(base["details"])["values"]
    count = 0
    for group, category in (("characters", "Legends"), ("weapons", "Weapons"), ("meleeWeapons", "Melee Weapons")):
        for entry in base_values.get(group, []):
            owner_path = entry.get("flavor", "")
            owner = by_guid.get(guid_text(owner_path)) if owner_path else None
            if owner is None or owner["status"] != "settings_decoded":
                continue
            owner_values = json.loads(owner["details"])["values"]
            owner_name, owner_key = localize(owner_values)
            if not owner_name:
                continue  # Raw data remains available in Advanced View.
            for declared in owner_values.get("skins", []):
                skin_path = declared.get("flavor", "")
                skin = by_guid.get(guid_text(skin_path)) if skin_path else None
                if skin is None or skin["status"] != "settings_decoded":
                    continue
                values = json.loads(skin["details"])["values"]
                if values.get("isTheFavoriteSentinel"):
                    continue
                # A declared parent is authoritative and must agree with the skin list.
                if values.get("parentItemFlavor") and guid_text(values["parentItemFlavor"]) != owner["guid"]:
                    continue
                skin_name, skin_key = localize(values)
                if not skin_name:
                    continue
                models = []
                for field in ("bodyModel", "armsModel", "worldModel", "viewModel"):
                    model_name = values.get(field)
                    if not model_name:
                        continue
                    original_guid = guid_text(model_name)
                    odl_path = values.get(field + "_odlBlob")
                    pak_name = None
                    evidence = []
                    if odl_path:
                        odl = by_guid.get(guid_text(odl_path))
                        if odl and odl["status"] == "on_demand_asset_decoded":
                            info = json.loads(odl["details"])
                            if info["original_guid"] != original_guid:
                                continue  # Never substitute a different model.
                            pak = by_guid.get(info["pak_guid"])
                            if pak and pak["status"] == "on_demand_package_decoded":
                                pak_name = json.loads(pak["details"])["pak_name"]
                                evidence = [odl["guid"], pak["guid"]]
                    models.append({"field": field, "name": model_name, "guid": original_guid,
                                   "pak_name": pak_name, "odl_evidence": evidence})
                evidence = {"base_guid": base["guid"], "owner_guid": owner["guid"], "skin_guid": skin["guid"],
                            "owner_localization_key": owner_key, "skin_localization_key": skin_key,
                            "feature_flag": declared.get("featureFlag", ""),
                            "shipping_status": owner_values.get("shippingStatus"),
                            "source": skin["path"], "skin_family": values.get("skinName", ""),
                            "payload_resolution": 'reconstructed_patch' if skin['patch_count'] else 'base_package',
                            "camo_index": values.get("camoIndex"), "models": models}
                db.execute("""INSERT INTO cosmetics(category,owner_guid,owner_name,skin_guid,name,quality,details)
                    VALUES(?,?,?,?,?,?,?)""", (category,owner["guid"],owner_name,skin["guid"],skin_name,
                    values.get("quality", ""),json.dumps(evidence, ensure_ascii=False)))
                count += 1
    return count
