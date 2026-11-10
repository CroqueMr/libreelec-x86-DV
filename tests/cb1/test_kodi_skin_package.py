"""Exercise native recipe cache invalidation and whole-skin installation."""
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]


class KodiSkinPackage(unittest.TestCase):
    def test_kodi_skin_consumer_tracks_its_parent_inputs(self):
        functions=(REPO/'config/functions').read_text(encoding='utf-8')
        build=(REPO/'scripts/build').read_text(encoding='utf-8')
        start=functions.index('calculate_stamp() {')
        calculate=functions[start:functions.index('\n}\n',start)+3]
        start=functions.index('    if [ -n "${PKG_DEPENDS_UNPACK}" ]; then',functions.index('source_package() {'))
        depend=functions[start:functions.index('\n    fi',start)+7]
        start=build.index('STAMP=${STAMPS}/${PKG_NAME}/build_${TARGET}')
        guard=build[start:build.index('\n${SCRIPTS}/unpack',start)]
        start=build.rindex('PKG_DEEPHASH=$(calculate_stamp)')
        stamp=build[start:build.index('\npkg_lock_status',start)]
        recipe=(REPO/'packages/mediacenter/kodi-theme-Estuary/package.mk').read_text(encoding='utf-8')
        cases=['project-patch','device-patch','project-create','device-create',
               'project-versioned','device-versioned','parent-package','project-package',
               'unrelated-package','without-device','unchanged']
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                pkg=root/'packages/mediacenter/kodi-theme-Estuary';pkg.mkdir(parents=True)
                (pkg/'package.mk').write_text(recipe,encoding='utf-8')
                parent=root/'packages/mediacenter/kodi';parent.mkdir()
                (parent/'package.mk').write_text('parent package inputs\n')
                project=root/'projects/Generic/patches/kodi';project.mkdir(parents=True)
                device=root/'projects/Generic/devices/Fixture/patches/kodi';device.mkdir(parents=True)
                for folder in (project,device):(folder/'kodi.patch').write_text('old patch\n')
                if case=='project-create':(project/'kodi.patch').unlink();project.rmdir()
                if case=='device-create':(device/'kodi.patch').unlink();device.rmdir()
                if case in ('project-versioned','device-versioned'):
                    versioned=(project if case=='project-versioned' else device)/'1.0/x86'
                    versioned.mkdir(parents=True);(versioned/'kodi.patch').write_text('old patch\n')
                project_pkg=root/'projects/Generic/packages/kodi';project_pkg.mkdir(parents=True)
                (project_pkg/'hook').write_text('old hook\n')
                unrelated=root/'packages/unrelated';unrelated.mkdir()
                (unrelated/'package.mk').write_text('old unrelated input\n')
                producer=root/'producer/.noinstall/skin.estuary';(producer/'xml').mkdir(parents=True)
                (producer/'xml/layout.xml').write_text('<theme revision="old"/>')
                (producer/'second-asset').write_text('old asset')
                script=root/'run.sh'
                script.write_text('''#!/bin/bash
set -e
ROOT="$1";cd "$ROOT"
PROJECT_DIR="$ROOT/projects";PROJECT=Generic;DEVICE="$2"
PKG_DIR="$ROOT/packages/mediacenter/kodi-theme-Estuary"
STAMPS="$ROOT/stamps";INSTALL="$ROOT/consumer";TARGET=target;BUILD_WITH_DEBUG=no
PKG_NEED_UNPACK=
get_pkg_directory() { printf '%s\\n' "$ROOT/packages/mediacenter/$1"; }
get_install_dir() { printf '%s\\n' "$ROOT/producer"; }
pkg_lock_status() { printf '%s\\n' "$4"; }
. "$PKG_DIR/package.mk"
'''+depend+'\n'+calculate+'''
mkdir -p "$STAMPS/$PKG_NAME"
calculate_stamp > "$ROOT/calculated-hash"
'''+guard+'\nmakeinstall_target\n'+stamp+'\n',encoding='utf-8')
                def run():
                    result=subprocess.run(['bash',str(script),str(root),'' if case=='without-device' else 'Fixture'],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    return result
                run();old_hash=(root/'calculated-hash').read_text()
                if case in ('project-patch','device-patch','without-device'):
                    folder=project if case=='project-patch' else device
                    (folder/'kodi.patch').write_text('new patch\n')
                if case in ('project-create','device-create'):
                    folder=project if case=='project-create' else device
                    folder.mkdir();(folder/'kodi.patch').write_text('new patch\n')
                if case in ('project-versioned','device-versioned'):(versioned/'kodi.patch').write_text('new patch\n')
                if case=='parent-package':(parent/'package.mk').write_text('new parent input\n')
                if case=='project-package':(project_pkg/'hook').write_text('new hook\n')
                if case=='unrelated-package':(unrelated/'package.mk').write_text('new unrelated input\n')
                changed=case not in ('unrelated-package','without-device','unchanged')
                if changed:
                    (producer/'xml/layout.xml').write_text('<theme revision="new"/>')
                    (producer/'second-asset').write_text('new asset')
                    (producer/'new-asset').write_text('new whole-skin member')
                result=run();new_hash=(root/'calculated-hash').read_text()
                consumer=root/'consumer/usr/share/kodi/addons/skin.estuary'
                self.assertEqual(old_hash!=new_hash,changed)
                self.assertEqual('already built' in result.stdout,not changed)
                self.assertEqual((consumer/'xml/layout.xml').read_text(),'<theme revision="new"/>' if changed else '<theme revision="old"/>')
                self.assertEqual((consumer/'second-asset').read_text(),'new asset' if changed else 'old asset')
                self.assertEqual((consumer/'new-asset').exists(),changed)
