"""Frozen desktop entrypoint uses absolute imports, unlike package __main__."""
import json
import sys
import tempfile
import traceback
import argparse
import time
from pathlib import Path
from apex_asset_studio.ui.app import main, ApexAssetStudioApp


def smoke_test(output, model_guid=None, family=None):
    """Exercise the packaged GUI and native modules without touching a user's catalog."""
    result = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False))}
    try:
        import ooz
        import texture2ddecoder
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix='aas-smoke-') as tmp:
            app = ApexAssetStudioApp(catalog_path=None if model_guid else Path(tmp)/'catalog.sqlite3')
            app.update()
            deadline=time.monotonic()+5
            while not app.preview.context_created and time.monotonic()<deadline:
                app.update();time.sleep(.02)
            assert app.preview.context_created
            result.update(title=app.title(), detected_install=app.game_path.get(),
                          export_disabled=app.export_btn.instate(['disabled']),
                          scan_label=app.scan_btn.cget('text'),
                          image_mode=Image.new('RGBA',(1,1)).mode,
                          appearance={'preset':app.appearance['preset'], 'layout':app.appearance['layout'],
                                      'mascot_loaded':hasattr(app, '_mascot_image')})
            assert result['export_disabled']
            assert result['appearance']['mascot_loaded']
            if model_guid:
                from OpenGL import GL
                from apex_asset_studio.repository import AssetRepository
                from apex_asset_studio.rpak.model import decode_model
                from apex_asset_studio.rpak.animation import decode_animation
                from apex_asset_studio.export.package import export_package
                with AssetRepository(app.catalog,app.game_path.get()) as repository:
                    archive,asset=repository.asset(model_guid)
                    model=decode_model(archive,asset,family)
                    rows=app.catalog.declared_animations(model.guid,model.rig_guids)
                    row=next(r for r in rows if Path(r['name']).stem=='idle_pistol_akimbo')
                    clip=decode_animation(repository,model,row['guid'],row['declared_rig_links'][0])
                app._model=model;app.lod_var.set('LOD 0');app._render_model()
                app.preview.set_pose(clip,min(10,clip['frames']-1));app.preview._display();GL.glFinish()
                assert GL.glGetError()==GL.GL_NO_ERROR
                path,manifest=export_package(model,app.catalog,app.game_path.get(),Path(tmp)/'exports','Frozen model probe',all_lods=True,animation=clip)
                textures=[t for m in manifest['materials'] for t in m.get('textures',[])]
                result['native_probe']={'guid':model.guid,'family':model.family,'bones':len(model.bones),
                    'lods':len(model.lods),'export_exists':path.exists(),
                    'reflected_texture_roles':sum(t['role']!='unresolved' for t in textures),
                    'derived_normal_maps':sum(bool(t.get('normal_conversion')) for t in textures),
                    'status':manifest['status'],'gpu_renderer':app.preview.renderer,
                    'preview_vertices':len(app.preview.vertices),'animation_frames':clip['frames'],
                    'export_default':app.export_path_var.get()}
            app.destroy()
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1

if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        parser=argparse.ArgumentParser()
        parser.add_argument('--smoke-test',required=True)
        parser.add_argument('--model-guid')
        parser.add_argument('--family')
        args=parser.parse_args()
        sys.exit(smoke_test(args.smoke_test,args.model_guid,args.family))
    main()
