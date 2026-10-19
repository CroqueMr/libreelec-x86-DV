# SPDX-License-Identifier: MIT
"""Current owner digests must not replace immutable extraction attribution."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cb1_verify',ROOT/'tools/verify.py')
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
NEW_OWNERS=('src/dvbridge_core.c','src/dvbridge_core.h','src/dvbridge_metadata.h','src/dvbridge_pack_sources.h.in',
            'src/cb1_circuit.c','src/cb1_circuit.h','src/cb1_l1l3_model.c','src/cb1_l1l3_model.h',
            'src/cb1_hdr10_features.c','src/cb1_hdr10_features.h',
            'src/cb1_hdr10_extrema.c','src/cb1_hdr10_extrema.h',
            'src/cb1_hdr10_quantiles.c','src/cb1_hdr10_quantiles.h',
            'src/cb1_hdr10_ingress.c','src/cb1_hdr10_ingress.h',
            'src/cb1_hdr10_statistics.c','src/cb1_hdr10_statistics.h',
            'src/cb1_hdr10_filter.c','src/cb1_hdr10_filter.h',
            'src/cb1_hdr10_spatial.c','src/cb1_hdr10_spatial.h',
            'src/cb1_hdr10_temporal.c','src/cb1_hdr10_temporal.h',
            'src/cb1_hdr10_ai.c','src/cb1_hdr10_ai.h')

class OwnedSources(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)/'source'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('.git','.superpowers','.evidence','__pycache__','*.pyc','build-output'))
        path=self.root/'config/owned-sources.json';self.owned=json.loads(path.read_text())
        for name in self.owned.keys() | set(NEW_OWNERS):self.owned[name]=verify.sha(self.root/name)
        self.save_owned()
    def tearDown(self):self.temporary.cleanup()
    def save_owned(self):
        (self.root/'config/owned-sources.json').write_text(json.dumps(self.owned)+'\n')
    def test_current_owned_helpers_preserve_historical_attribution(self):
        verify.verify(self.root)
    def test_missing_owned_helper_fails(self):
        self.owned.pop('src/dvbridge_metadata.h');self.save_owned()
        with self.assertRaisesRegex(ValueError,'owned source identity'):verify.verify(self.root)
    def test_importer_override_retains_its_historical_extraction_record(self):
        origins=json.loads((self.root/'config/extraction-origins.json').read_text())
        self.assertIn('src/dvbridge_dmabuf.c',origins['files'])
        self.assertIn('src/dvbridge_dmabuf.c',self.owned)
        self.assertNotEqual(origins['files']['src/dvbridge_dmabuf.c']['sha256'],self.owned['src/dvbridge_dmabuf.c'])
        verify.verify(self.root)
    def test_fel_device_fix_retains_its_historical_extraction_record(self):
        origins=json.loads((self.root/'config/extraction-origins.json').read_text())
        self.assertNotEqual(origins['files']['src/dvbridge_fel.c']['sha256'],
                            self.owned['src/dvbridge_fel.c'])
        verify.verify(self.root)
    def test_wrong_current_owned_digest_fails(self):
        self.owned['src/dvbridge_metadata.h']='0'*64;self.save_owned()
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):verify.verify(self.root)
    def test_modified_master_descriptor_fails(self):
        path=self.root/'src/cb1_master_reference.h'
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):verify.verify(self.root)
    def test_modified_master_shader_owner_fails(self):
        path=self.root/'patches/libplacebo/libplacebo-9913-processing.patch'
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):verify.verify(self.root)
    def test_wrong_historical_provenance_fails(self):
        path=self.root/'src/PROVENANCE.json';receipt=json.loads(path.read_text())
        receipt['files']['dvbridge_metadata.h']='0'*64;path.write_text(json.dumps(receipt))
        original=verify.sha(ROOT/'src/PROVENANCE.json');real_sha=verify.sha
        # Isolate the attribution check after the already qualified outer digest
        # edge. Do not add PROVENANCE to the current-owned override list.
        with patch.object(verify,'sha',side_effect=lambda p:original if p==path else real_sha(p)):
            with self.assertRaisesRegex(ValueError,'provenance/origin mismatch'):verify.verify(self.root)
    def test_unexpected_source_fails(self):
        (self.root/'src/unexpected.h').write_text('/* undeclared */\n')
        with self.assertRaisesRegex(ValueError,'Unexpected or missing runtime source'):verify.verify(self.root)
    def test_modified_model_fails(self):
        path=self.root/'models/l1l3/data/field-0.txt'
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):verify.verify(self.root)
    def test_missing_model_fails(self):
        (self.root/'models/l1l3/data/normalization.f32').unlink()
        with self.assertRaises((ValueError,OSError)):verify.verify(self.root)

if __name__=='__main__':unittest.main()
