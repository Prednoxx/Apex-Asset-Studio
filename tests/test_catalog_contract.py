import sqlite3
import json
import tempfile
import unittest
from pathlib import Path

from apex_asset_studio.catalog import Catalog, INDEX_VERSION


class CatalogContractTests(unittest.TestCase):
    def test_animation_links_require_exact_decoded_header_guids(self):
        with tempfile.TemporaryDirectory() as td:
            cat=Catalog(Path(td)/'catalog.sqlite3')
            with cat.connect() as db:
                db.execute("INSERT INTO containers(id,path,filename,status) VALUES(1,'test.rpak','test.rpak','ok')")
                fixtures=[('RIG','arig',{'declared_sequences':['SEQ']},'animation_header_decoded'),
                          ('SEQ','aseq',{},'animation_header_decoded'),
                          ('DIRECT','aseq',{'declared_models':['MODEL']},'animation_header_decoded'),
                          ('SUBSTRING','aseq',{'declared_models':['MODEL_SUFFIX']},'animation_header_decoded'),
                          ('UNRESOLVED','aseq',{'declared_models':['MODEL']},'unresolved')]
                for i,(guid,kind,details,status) in enumerate(fixtures):
                    cur=db.execute('INSERT INTO assets(container_id,ordinal,guid,type) VALUES(1,?,?,?)',(i,guid,kind))
                    db.execute('INSERT INTO asset_details(asset_id,name,status,details) VALUES(?,?,?,?)',
                               (cur.lastrowid,guid,status,json.dumps(details)))
            rows=cat.declared_animations('MODEL',['RIG'])
            self.assertEqual({r['guid'] for r in rows},{'SEQ','DIRECT'})
            self.assertTrue(all(r['track_status']=='not_decoded' for r in rows))

    def test_simple_sections_only_reflect_real_rows(self):
        with tempfile.TemporaryDirectory() as td:
            cat = Catalog(Path(td) / "catalog.sqlite3")
            with cat.connect() as db:
                db.execute("INSERT INTO meta(key,value) VALUES('index_version',?)", (INDEX_VERSION,))
                db.execute(
                    "INSERT INTO containers(path,filename,status,mtime) VALUES(?,?,?,?)",
                    ("C:/fake/a.rpak", "a.rpak", "ok", 1.0),
                )
                cid = db.execute("SELECT id FROM containers WHERE path='C:/fake/a.rpak'").fetchone()[0]
                db.execute(
                    "INSERT INTO assets(container_id,ordinal,guid,type,version,header_size) VALUES(?,?,?,?,?,?)",
                    (cid, 0, "0000000000000001", "mdl_", 1, 64),
                )
                db.execute(
                    "INSERT INTO assets(container_id,ordinal,guid,type,version,header_size) VALUES(?,?,?,?,?,?)",
                    (cid, 1, "0000000000000002", "uiia", 1, 64),
                )
            cat._index_outdated = False
            sections = cat.simple_sections()
            self.assertEqual([s["label"] for s in sections], ["Models", "UI Images"])
            self.assertNotIn("Legends", [s["label"] for s in sections])

    def test_failure_groups_collapse_repeated_errors(self):
        with tempfile.TemporaryDirectory() as td:
            cat = Catalog(Path(td) / "catalog.sqlite3")
            with cat.connect() as db:
                for i in range(3):
                    db.execute(
                        "INSERT INTO containers(path,filename,status,error,compression,mtime) VALUES(?,?,?,?,?,?)",
                        (f"C:/fake/{i}.rpak", f"{i}.rpak", "error", "same failure", "Oodle", 1.0),
                    )
            groups = cat.failure_groups()
            self.assertEqual(groups[0]["n"], 3)
            self.assertEqual(groups[0]["error"], "same failure")


if __name__ == "__main__":
    unittest.main()
