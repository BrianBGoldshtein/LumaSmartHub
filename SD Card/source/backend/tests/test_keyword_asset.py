import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from luma import keyword_asset as asset
from luma.keyword_wake import MODEL_PINS


def test_source_pins_match_the_actual_model_factory_and_arm64_recipe():
    assert {name.split('/')[1]:record['sha256'] for name,record in asset.PINNED_FILES.items()
            if name.startswith('model/')} == MODEL_PINS
    assert len([name for name in asset.PINNED_FILES if name.startswith('wheels/')]) == 3
    assert all(type(record['size']) is int and 0<record['size']<=asset.MAX_MEMBER_BYTES
               and len(record['sha256'])==64 for record in asset.PINNED_FILES.values())
    assert sum(record['size'] for record in asset.PINNED_FILES.values())<asset.MAX_ASSET_BYTES


@pytest.fixture
def package(tmp_path,monkeypatch):
    payload = {name:('fixture '+name).encode() for name in asset.PINNED_FILES}
    payload['NOTICE.txt'] = asset.NOTICE
    monkeypatch.setattr(asset,'PINNED_FILES',{name:{'size':len(data),
        'sha256':hashlib.sha256(data).hexdigest()} for name,data in payload.items()})
    key = Ed25519PrivateKey.generate()
    public = tmp_path/'update.pub'
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo))
    def make(*, manifest=None, signature=None, extra=None, changes=None, name='wake.lka'):
        raw = asset.canonical(manifest or asset.expected_manifest())
        path = tmp_path/name
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('manifest.json',raw)
            archive.writestr('manifest.sig',key.sign(raw) if signature is None else signature)
            for filename,data in {**payload,**(changes or {})}.items():
                archive.writestr(filename,data)
            if extra:
                for filename,data in extra.items():
                    archive.writestr(filename,data)
        return path
    return SimpleNamespace(make=make,public=public,key=key,payload=payload)


def test_signature_and_pins_allow_only_the_expected_files(tmp_path,package):
    stage = tmp_path/'stage'; stage.mkdir()
    assert asset.verify_and_extract(package.make(),stage,package.public)==asset.expected_manifest()
    assert (stage/'manifest.sig').stat().st_size==64
    for name,data in package.payload.items():
        assert (stage/name).read_bytes()==data


@pytest.mark.parametrize('extra', ['../../outside','wheels/unpinned.whl','manifest.json'])
def test_even_signed_traversal_extra_or_duplicate_is_rejected_before_writes(tmp_path,package,extra):
    stage = tmp_path/'stage'; stage.mkdir()
    with pytest.raises(asset.KeywordAssetError,match='keyword_package_layout_invalid'):
        asset.verify_and_extract(package.make(extra={extra:b'no'}),stage,package.public)
    assert not list(stage.iterdir())
    assert not (tmp_path/'outside').exists()


@pytest.mark.parametrize('field,value', [('version','0.2.8'),('python','cp311-aarch64'),
    ('keyword_id','unreviewed'),('format',True),('kind','luma-offline-voice')])
def test_wrong_version_kind_architecture_and_boolean_format_are_not_compatible(tmp_path,package,field,value):
    manifest = asset.expected_manifest(); manifest[field]=value
    stage = tmp_path/'stage'; stage.mkdir()
    with pytest.raises(asset.KeywordAssetError,match='keyword_manifest_invalid'):
        asset.verify_and_extract(package.make(manifest=manifest),stage,package.public)
    assert not list(stage.iterdir())


def test_bad_signature_cannot_execute_or_extract(tmp_path,package):
    stage = tmp_path/'stage'; stage.mkdir()
    with pytest.raises(asset.KeywordAssetError,match='keyword_signature_invalid'):
        asset.verify_and_extract(package.make(signature=bytes(64)),stage,package.public)
    assert not list(stage.iterdir())


def test_owner_signature_cannot_override_vendor_pins(tmp_path,package):
    manifest = asset.expected_manifest()
    manifest['files'] = {**manifest['files'],'model/new.onnx':{'size':3,'sha256':hashlib.sha256(b'new').hexdigest()}}
    stage = tmp_path/'stage'; stage.mkdir()
    with pytest.raises(asset.KeywordAssetError):
        asset.verify_and_extract(package.make(manifest=manifest,extra={'model/new.onnx':b'new'}),stage,package.public)


@pytest.mark.parametrize('same_size',[True,False])
def test_changed_payload_fails_its_signed_hash_or_size(tmp_path,package,same_size):
    name = next(name for name in package.payload if name.startswith('model/'))
    bad = b'x'*len(package.payload[name]) if same_size else b'changed'
    stage = tmp_path/'stage'; stage.mkdir()
    with pytest.raises(asset.KeywordAssetError,match='keyword_file_invalid'):
        asset.verify_and_extract(package.make(changes={name:bad}),stage,package.public)


@pytest.mark.skipif(sys.platform!='linux',reason='appliance filesystem guard')
def test_extraction_does_not_follow_existing_parent_links(tmp_path,package):
    stage = tmp_path/'stage'; stage.mkdir()
    outside = tmp_path/'outside'; outside.mkdir()
    (stage/'model').symlink_to(outside,target_is_directory=True)
    with pytest.raises(asset.KeywordAssetError,match='keyword_storage_invalid'):
        asset.verify_and_extract(package.make(),stage,package.public)
    assert not list(outside.iterdir())


def test_smoke_requires_exact_negative_response_not_just_ready_or_import():
    valid = b'KWS02\n'+struct.pack('>Bdd',0,-1,-1)
    asset.check_worker_smoke(valid)
    for data in (b'KWS02\n',valid+b'extra',valid[:-1],b'MODEL\n',
                 b'KWS02\n'+struct.pack('>Bdd',1,0,.1),b'KWS02\n'+struct.pack('>Bdd',2,-1,-1),
                 b'READY\n'+struct.pack('>Bd',0,-1)):
        with pytest.raises(asset.KeywordAssetError,match='keyword_smoke_failed'):
            asset.check_worker_smoke(data)


@pytest.fixture
def installation(tmp_path,monkeypatch,package):
    if sys.platform!='linux':
        pytest.skip('transactional appliance installation')
    monkeypatch.setattr(asset,'_runtime_supported',lambda:True)
    root = tmp_path/'keyword-assets'
    settings = tmp_path/'settings-and-accounts.json'
    settings.write_bytes(b'saved state sentinel; not real account data')
    commands = []
    def run(command,**kwargs):
        commands.append((command,kwargs))
        if command[1:3]==['-m','venv']:
            python = Path(command[3])/'bin/python'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'unit fake interpreter, never executed')
        if '-I' in command:
            assert kwargs['input']==struct.pack('>I',8000)+bytes(8000)
            return SimpleNamespace(stdout=b'KWS02\n'+struct.pack('>Bdd',0,-1,-1))
        return SimpleNamespace(stdout=b'')
    yield SimpleNamespace(root=root,run=run,commands=commands,settings=settings)
    assert settings.read_bytes()==b'saved state sentinel; not real account data'


def install(package,installation,**kwargs):
    return asset.install_asset(package.make(),root=installation.root,public_key=package.public,
                               run=kwargs.pop('run',installation.run),**kwargs)


def test_install_checks_staged_and_relocated_worker_without_changing_app_or_settings(package,installation):
    assert install(package,installation)=={'phase':'ready','installed':True}
    assert asset.ready(installation.root,package.public)
    calls = [command for command,kwargs in installation.commands if '-I' in command]
    assert len(calls)==2 and '.keyword-stage-' in calls[0][0] and asset.KEYWORD_ID in calls[1][0]
    pip = next(command for command,kwargs in installation.commands if 'pip' in command)
    assert {'--no-index','--no-deps','--no-cache-dir'}.issubset(pip)
    assert not (installation.root/'install.json').exists()
    assert not list(installation.root.glob('.keyword-stage-*'))
    assert not list(installation.root.glob('.keyword-previous-*'))
    count = len(installation.commands)
    assert install(package,installation)=={'phase':'ready','installed':False}
    assert len(installation.commands)==count


def test_files_presence_does_not_mean_ready(package,installation):
    installation.root.mkdir(mode=0o700)
    folder = installation.root/asset.KEYWORD_ID
    folder.mkdir(parents=True,mode=0o700)
    assert not asset.ready(installation.root,package.public)
    with pytest.raises(asset.KeywordAssetError,match='keyword_recovery_required'):
        install(package,installation)


def test_failed_final_protocol_restores_the_previous_asset(package,installation):
    install(package,installation)
    old_token = asset._read_small(installation.root/asset.KEYWORD_ID/'ownership.json')['token']
    def fail_final(command,**kwargs):
        result = installation.run(command,**kwargs)
        if '-I' in command and '.keyword-stage-' not in command[0]:
            result.stdout = b'KWS02\n'+struct.pack('>Bdd',2,-1,-1)
        return result
    with pytest.raises(asset.KeywordAssetError,match='keyword_smoke_failed'):
        install(package,installation,run=fail_final,replace_existing=True)
    assert asset.ready(installation.root,package.public)
    assert asset._read_small(installation.root/asset.KEYWORD_ID/'ownership.json')['token']==old_token
    assert asset._read_small(installation.root/'status.json')['phase']=='failed'
    assert not (installation.root/'install.json').exists()


def test_failed_first_install_is_not_marked_ready(package,installation):
    def failure(command,**kwargs):
        if '-I' in command:
            raise subprocess.TimeoutExpired(command,90)
        return installation.run(command,**kwargs)
    with pytest.raises(asset.KeywordAssetError,match='keyword_install_failed'):
        install(package,installation,run=failure)
    assert not asset.ready(installation.root,package.public)
    assert not (installation.root/asset.KEYWORD_ID).exists()
    assert not (installation.root/'install.json').exists()


class PowerLoss(BaseException):
    pass


@pytest.mark.parametrize('point',['staging','switching','previous-renamed','new-renamed','ready-before-commit','committed'])
def test_power_loss_recovers_only_identified_owned_directories(package,installation,monkeypatch,point):
    install(package,installation)
    old_token = asset._read_small(installation.root/asset.KEYWORD_ID/'ownership.json')['token']
    original_json, original_replace = asset._atomic_json,asset.os.replace
    def crash_json(path,value):
        original_json(path,value)
        if ((path.name=='install.json' and value.get('phase')==point)
                or (point=='ready-before-commit' and path.name=='ready.json')):
            raise PowerLoss
    def crash_replace(source,target):
        original_replace(source,target)
        if ((point=='previous-renamed' and Path(target).name.startswith('.keyword-previous-'))
                or (point=='new-renamed' and Path(source).name.startswith('.keyword-stage-')
                    and Path(target).name==asset.KEYWORD_ID)):
            raise PowerLoss
    with monkeypatch.context() as crash:
        crash.setattr(asset,'_atomic_json',crash_json)
        crash.setattr(asset.os,'replace',crash_replace)
        with pytest.raises(PowerLoss):
            install(package,installation,replace_existing=True)
    assert asset.recover_interrupted_install(installation.root,package.public)
    assert asset.ready(installation.root,package.public)
    token = asset._read_small(installation.root/asset.KEYWORD_ID/'ownership.json')['token']
    assert (token!=old_token) if point=='committed' else (token==old_token)
    assert not (installation.root/'install.json').exists()
    assert not list(installation.root.glob('.keyword-stage-*'))
    assert not list(installation.root.glob('.keyword-previous-*'))


def test_unrecognized_previous_folder_is_preserved(package,installation):
    install(package,installation)
    folder = installation.root/('.keyword-previous-'+asset.KEYWORD_ID)
    folder.mkdir(); (folder/'keep.txt').write_bytes(b'not installer-owned')
    with pytest.raises(asset.KeywordAssetError,match='keyword_recovery_required'):
        asset.recover_interrupted_install(installation.root,package.public)
    assert (folder/'keep.txt').read_bytes()==b'not installer-owned'
    assert asset.ready(installation.root,package.public)


def test_concurrent_installer_cannot_enter_transaction(package,installation):
    with asset.installation_lock(installation.root):
        with pytest.raises(asset.KeywordAssetError,match='keyword_asset_busy'):
            install(package,installation)
    assert not installation.commands


@pytest.mark.parametrize('state',['[]','null','{"phase":"switching"}','{"format":true}'])
def test_malformed_journal_is_not_permission_to_remove_data(package,installation,state):
    install(package,installation)
    (installation.root/'install.json').write_text(state)
    with pytest.raises(asset.KeywordAssetError,match='keyword_recovery_required'):
        asset.recover_interrupted_install(installation.root,package.public)
    assert asset.ready(installation.root,package.public)


def test_storage_and_wrong_runtime_fail_before_mutations(package,installation,monkeypatch,tmp_path):
    monkeypatch.setattr(asset,'_runtime_supported',lambda:False)
    with pytest.raises(asset.KeywordAssetError,match='keyword_runtime_unsupported'):
        install(package,installation)
    assert not installation.root.exists()
    monkeypatch.setattr(asset,'_runtime_supported',lambda:True)
    monkeypatch.setattr(asset.shutil,'disk_usage',lambda _:SimpleNamespace(free=1))
    with pytest.raises(asset.KeywordAssetError,match='keyword_storage_full'):
        install(package,installation)
    assert not (installation.root/'install.json').exists()
    outside = tmp_path/'outside'; outside.mkdir()
    linked = tmp_path/'linked'; linked.symlink_to(outside,target_is_directory=True)
    with pytest.raises(asset.KeywordAssetError,match='keyword_storage_invalid'):
        asset.install_asset(package.make(),root=linked,public_key=package.public,run=installation.run)
    assert not list(outside.iterdir())


def test_builder_deterministically_signs_pins_and_never_bundles_key(tmp_path,package):
    tool = Path(__file__).parents[2]/'tools/build-keyword-asset.py'
    specification = importlib.util.spec_from_file_location('build_keyword_asset',tool)
    builder = importlib.util.module_from_spec(specification); specification.loader.exec_module(builder)
    root = tmp_path/'delivery'; (root/'source/system').mkdir(parents=True)
    (root/'source/system/luma-update-ed25519.pub').write_bytes(package.public.read_bytes())
    assets = tmp_path/'vendor'
    for name,data in package.payload.items():
        if name=='NOTICE.txt':
            continue
        path = assets/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    key_path = tmp_path/'private.pem'
    key_path.write_bytes(package.key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,serialization.NoEncryption())); key_path.chmod(0o600)
    arguments = dict(root=root,model=assets/'model',wheels=assets/'wheels',
        model_card=assets/'licenses/model-card.txt',license_text=assets/'licenses/Apache-2.0.txt',key_path=key_path)
    first,second = tmp_path/'first.lka',tmp_path/'second.lka'
    assert builder.build(**arguments,output=first)['sha256']==builder.build(**arguments,output=second)['sha256']
    stage = tmp_path/'built-stage'; stage.mkdir()
    asset.verify_and_extract(first,stage,package.public)
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist())==set(asset.PINNED_FILES)|{'manifest.json','manifest.sig'}
        assert not any('private' in name or name.endswith('.pem') for name in archive.namelist())
    with pytest.raises(ValueError):
        builder.build(**arguments,output=first)
    bad_key = tmp_path/'wrong.pem'
    bad_key.write_bytes(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,serialization.NoEncryption())); bad_key.chmod(0o600)
    with pytest.raises(ValueError,match='does not match'):
        builder.build(**{**arguments,'key_path':bad_key},output=tmp_path/'wrong.lka')
    name = next(name for name in package.payload if name.startswith('model/'))
    (assets/name).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='source pin'):
        builder.build(**arguments,output=tmp_path/'corrupt.lka')


class Response(io.BytesIO):
    def __init__(self,data,url,headers=None):
        super().__init__(data)
        self.url,self.headers = url,headers or {}
    def geturl(self):
        return self.url


@pytest.fixture
def feed(package,installation):
    data = package.make().read_bytes()
    entry = {'name':asset.ASSET_NAME,'size':len(data),'browser_download_url':asset.DOWNLOAD_URL,
             'digest':'sha256:'+hashlib.sha256(data).hexdigest()}
    metadata = {'draft':False,'prerelease':False,'target_commitish':'main',
                'tag_name':'v'+asset.ASSET_VERSION,'assets':[entry]}
    calls = []
    state = SimpleNamespace(data=data,metadata=metadata,calls=calls,
        metadata_url=asset.RELEASE_URL,download_url='https://release-assets.githubusercontent.com/asset',
        headers={'Content-Length':str(len(data))})
    def open_(request,**kwargs):
        calls.append(request.full_url)
        if request.full_url==asset.RELEASE_URL:
            return Response(json.dumps(state.metadata).encode(),state.metadata_url)
        assert request.full_url==asset.DOWNLOAD_URL
        return Response(state.data,state.download_url,state.headers)
    state.opener = SimpleNamespace(open=open_)
    return state


def fetch(package,installation,feed,**kwargs):
    return asset.fetch_and_install(root=installation.root,public_key=package.public,
        opener=feed.opener,installer=lambda bundle,**options:asset.install_asset(
            bundle,run=installation.run,**options),**kwargs)


def test_download_installs_only_a_verified_main_sidecar_and_cleans_private_temporary(package,installation,feed):
    assert fetch(package,installation,feed)=={'phase':'ready','installed':True}
    assert feed.calls==[asset.RELEASE_URL,asset.DOWNLOAD_URL]
    assert not list(installation.root.glob('.keyword-download-*'))
    assert asset.status(installation.root,package.public)['asset_available']
    feed.calls.clear()
    assert fetch(package,installation,feed)=={'phase':'ready','installed':False}
    assert not feed.calls


@pytest.mark.parametrize('field,value',[('draft',True),('prerelease',True),
    ('target_commitish','codex/test'),('tag_name','v0.2.8'),('assets',[])])
def test_wrong_release_is_rejected_before_binary_download(package,installation,feed,field,value):
    feed.metadata[field]=value
    with pytest.raises(asset.KeywordAssetError):
        fetch(package,installation,feed)
    assert feed.calls==[asset.RELEASE_URL]
    assert not installation.commands


@pytest.mark.parametrize('field,value',[('size',True),('size',0),('size',asset.MAX_ASSET_BYTES+1),
    ('browser_download_url','https://example.com/evil.lka'),('digest','not-a-digest')])
def test_bad_asset_metadata_cannot_select_an_arbitrary_url(package,installation,feed,field,value):
    feed.metadata['assets'][0][field]=value
    with pytest.raises(asset.KeywordAssetError,match='keyword_release_invalid'):
        fetch(package,installation,feed)
    assert feed.calls==[asset.RELEASE_URL]


@pytest.mark.parametrize('url',['http://github.com/asset','https://evil.example/asset',
    'https://user:password@github.com/asset','https://github.com:8443/asset'])
def test_invalid_download_redirects_do_not_reach_installer(package,installation,feed,url):
    feed.download_url=url
    with pytest.raises(asset.KeywordAssetError,match='keyword_download_address_invalid'):
        fetch(package,installation,feed)
    assert not installation.commands
    assert not list(installation.root.glob('.keyword-download-*'))


@pytest.mark.parametrize('change',['truncated','larger','wrong-digest','bad-length','invalid-signature'])
def test_corrupted_transfer_never_becomes_a_ready_model(package,installation,feed,change):
    if change=='truncated':
        feed.data=feed.data[:-1]
    elif change=='larger':
        feed.data+=b'x'
    elif change=='wrong-digest':
        feed.metadata['assets'][0]['digest']='sha256:'+'0'*64
    elif change=='bad-length':
        feed.headers['Content-Length']='not a length'
    else:
        feed.data=package.make(signature=bytes(64),name='bad-signature.lka').read_bytes()
        feed.metadata['assets'][0]['size']=len(feed.data)
        feed.metadata['assets'][0]['digest']='sha256:'+hashlib.sha256(feed.data).hexdigest()
        feed.headers['Content-Length']=str(len(feed.data))
    with pytest.raises(asset.KeywordAssetError):
        fetch(package,installation,feed)
    assert not asset.ready(installation.root,package.public)
    assert not installation.commands
    assert not list(installation.root.glob('.keyword-download-*'))


def test_download_has_a_total_deadline(package,installation,feed,monkeypatch):
    ticks=iter([0,301])
    monkeypatch.setattr(asset,'monotonic',lambda:next(ticks))
    with pytest.raises(asset.KeywordAssetError,match='keyword_download_timeout'):
        fetch(package,installation,feed)
    assert not installation.commands


def test_duplicate_asset_and_metadata_redirect_are_rejected(package,installation,feed):
    feed.metadata['assets'].append(dict(feed.metadata['assets'][0]))
    with pytest.raises(asset.KeywordAssetError,match='keyword_release_missing'):
        fetch(package,installation,feed)
    feed.metadata['assets']=feed.metadata['assets'][:1]
    feed.metadata_url='https://api.github.com/unexpected'
    with pytest.raises(asset.KeywordAssetError,match='keyword_release_invalid'):
        fetch(package,installation,feed)


def test_network_failure_preserves_the_previous_model(package,installation,feed):
    install(package,installation)
    old_token = asset._read_small(installation.root/asset.KEYWORD_ID/'ownership.json')['token']
    def failed(*args,**kwargs):
        raise OSError('private network detail')
    feed.opener.open=failed
    with pytest.raises(asset.KeywordAssetError,match='^keyword_download_failed$'):
        fetch(package,installation,feed,replace_existing=True)
    assert asset.ready(installation.root,package.public)
    assert asset._read_small(installation.root/asset.KEYWORD_ID/'ownership.json')['token']==old_token
    assert asset.status(installation.root,package.public)['error']=='keyword_download_failed'


def test_status_never_reports_a_file_presence_only_model_as_ready(package,installation):
    installation.root.mkdir(mode=0o700)
    asset.write_status(installation.root,'ready')
    assert asset.status(installation.root,package.public)['error']=='keyword_files_need_repair'
    for data in ('[]','null','{"phase":[]}','{"phase":"ready","error":"private details"}'):
        (installation.root/'status.json').write_text(data)
        assert asset.status(installation.root,package.public)['phase']=='not_installed'


def test_fifo_lock_does_not_hang_and_unsafe_storage_gets_no_failure_write(package,installation,feed):
    installation.root.mkdir(mode=0o700)
    os.mkfifo(installation.root/'.install.lock')
    with pytest.raises(asset.KeywordAssetError,match='keyword_storage_invalid'):
        install(package,installation)
    (installation.root/'.install.lock').unlink()
    installation.root.chmod(0o755)
    with pytest.raises(asset.KeywordAssetError,match='keyword_storage_invalid'):
        fetch(package,installation,feed)
    assert not (installation.root/'status.json').exists()
    assert not installation.commands
