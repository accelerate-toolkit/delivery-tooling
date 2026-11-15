import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { makePlan, bumpFor, artifactBundle, assertPlan, jsonBytes, sha256, configFrom } from '../release/core.mjs';
import { publishRelease } from '../release/publish.mjs';
import { GitHub } from '../release/github.mjs';

function fixture(t, policy = {}) {
  const cwd = mkdtempSync(path.join(tmpdir(), 'release-test-'));
  t.after(() => rmSync(cwd, { recursive: true, force: true }));
  const git = (...args) => execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }).trim();
  git('init', '-b', 'main'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid');
  const config = { schemaVersion: 1, streams: { main: { tagPrefix: 'v', initialVersion: '0.1.0', requiredChecks: ['check'], ...policy } } };
  writeFileSync(path.join(cwd, 'release.json'), JSON.stringify(config));
  git('add', 'release.json'); git('commit', '-m', 'chore: configure releases');
  const commit = message => { git('commit', '--allow-empty', '-m', message); return git('rev-parse', 'HEAD'); };
  const plan = () => makePlan({ cwd, repository: 'example/project' });
  return { cwd, git, commit, plan, config };
}

class FakeGitHub {
  repository = 'example/project';
  tags = new Map(); releases = new Map(); data = new Map(); mutations = []; nextId = 1;
  checksPass = true; uploadFailure = null; raceTag = false; raceDraft = false; raceUpload = false;
  assertChecks(sha, names) { this.checked = { sha, names }; if (!this.checksPass) throw new Error('Required check failed'); }
  getTag(tag) { return this.tags.get(tag) ?? null; }
  createTag(tag, sha) { this.tags.set(tag, sha); this.mutations.push('tag'); if (this.raceTag) throw new Error('Concurrent tag'); }
  getRelease(tag) { return this.releases.get(tag) ?? null; }
  createDraft(plan, body) {
    const release = { id: this.nextId++, tag_name: plan.tag, target_commitish: plan.sourceCommit, body, draft: true, html_url: 'https://example.invalid/release' };
    this.releases.set(plan.tag, release); this.mutations.push('draft');
    if (this.raceDraft) throw new Error('Concurrent draft');
    return release;
  }
  assets(id) { return [...this.data.values()].filter(asset => asset.release === id).map(({ bytes, ...asset }) => asset); }
  download(id) { return this.data.get(id).bytes; }
  upload(release, name, bytes) {
    if (this.uploadFailure === name) throw new Error('Interrupted upload');
    const id = this.nextId++;
    this.data.set(id, { id, release, name, bytes, size: bytes.length, state: 'uploaded' });
    this.mutations.push(`upload:${name}`);
    if (this.raceUpload) throw new Error('Concurrent upload');
  }
  publish(id) {
    const release = [...this.releases.values()].find(r => r.id === id);
    release.draft = false; this.mutations.push('publish'); return release;
  }
}

function prepared(t, artifacts = []) {
  const repo = fixture(t, { artifacts }); repo.commit('feat: ship a component\n\nExplain the change.');
  const plan = repo.plan();
  const directory = artifacts.length ? path.join(repo.cwd, 'dist') : undefined;
  if (directory) { mkdirSync(directory); for (const name of artifacts) writeFileSync(path.join(directory, name), `bytes for ${name}`); }
  const { manifest, files } = artifactBundle(plan, directory);
  const remote = new FakeGitHub();
  const args = { plan, directory, manifest, remote, cwd: repo.cwd, expectedCommit: plan.sourceCommit };
  return { ...repo, args, remote, plan, directory, manifest, files };
}

test('Conventional Commit library preserves the organization bump policy', () => {
  assert.equal(bumpFor(['docs: clarify', 'chore(deps): tools']), null);
  assert.equal(bumpFor(['perf: faster']), 'patch');
  assert.equal(bumpFor(['fix: repair', 'feat(api): add field']), 'minor');
  assert.equal(bumpFor(['feat(api)!: remove field']), 'major');
  assert.equal(bumpFor(['fix: change\n\nBREAKING CHANGE: migrate consumers']), 'major');
  assert.equal(bumpFor(['fix: change\n\nBREAKING-CHANGE: migrate consumers']), 'major');
});
test('no-release, initial release, notes and 0.x breaking transition', t => {
  const repo = fixture(t);
  assert.equal(repo.plan().release, false);
  repo.commit('feat: first feature\n\nUseful body.');
  const initial = repo.plan(); assert.equal(initial.version, '0.1.0'); assert.match(initial.notes, /Useful body/);
  repo.git('tag', initial.tag); repo.commit('fix!: change contract');
  assert.equal(repo.plan().version, '1.0.0');
});
test('initial breaking change starts at 1.0.0', t => {
  const repo = fixture(t); repo.commit('feat!: first breaking interface'); assert.equal(repo.plan().version, '1.0.0');
});
test('legacy tag continuity ignores unreachable high versions', t => {
  const repo = fixture(t, { tagPrefix: 'new-v', legacyTagPrefixes: ['old-v'] });
  repo.git('tag', 'old-v2.3.4'); repo.git('checkout', '-b', 'other'); repo.commit('feat: unrelated'); repo.git('tag', 'new-v99.0.0'); repo.git('checkout', 'main');
  repo.commit('fix: repair'); assert.equal(repo.plan().tag, 'new-v2.3.5');
});
test('stream paths exclude unrelated changes', t => {
  const repo = fixture(t, { paths: ['component'] });
  repo.commit('feat: unrelated'); assert.equal(repo.plan().release, false);
  mkdirSync(path.join(repo.cwd, 'component')); writeFileSync(path.join(repo.cwd, 'component', 'source'), 'x');
  repo.git('add', 'component'); repo.git('commit', '-m', 'feat: component'); assert.equal(repo.plan().version, '0.1.0');
});
test('rejects shallow history', t => {
  const repo = fixture(t); const clone = path.join(repo.cwd, 'shallow');
  execFileSync('git', ['clone', '--depth=1', `file://${repo.cwd}`, clone], { stdio: 'pipe' });
  assert.throws(() => makePlan({ cwd: clone, repository: 'example/project' }), /complete history/);
});
test('rejects unknown config fields, shared tag prefixes and reserved assets', () => {
  const policy = { tagPrefix: 'v', initialVersion: '0.1.0', requiredChecks: ['check'] };
  assert.throws(() => configFrom(JSON.stringify({ schemaVersion: 1, command: 'make build', streams: { main: policy } })), /Invalid release config/);
  assert.throws(() => configFrom(JSON.stringify({ schemaVersion: 1, streams: { one: policy, two: policy } })), /share tag prefix/);
  assert.throws(() => configFrom(JSON.stringify({ schemaVersion: 1, streams: { main: { ...policy, artifacts: ['SHA256SUMS'] } } })), /reserved/);
});
test('plan mutation fails digest verification', t => {
  const { plan } = prepared(t); assert.throws(() => assertPlan({ ...plan, sourceCommit: 'a'.repeat(40) }), /digest/);
});
test('exact artifact set rejects missing, extra and symlinked files', t => {
  const item = prepared(t, ['app.tar.gz']);
  writeFileSync(path.join(item.directory, 'extra'), 'x'); assert.throws(() => artifactBundle(item.plan, item.directory), /exact expected set/);
  rmSync(path.join(item.directory, 'extra')); rmSync(path.join(item.directory, 'app.tar.gz'));
  assert.throws(() => artifactBundle(item.plan, item.directory), /exact expected set/);
  symlinkSync(path.join(item.cwd, 'release.json'), path.join(item.directory, 'app.tar.gz'));
  assert.throws(() => artifactBundle(item.plan, item.directory), /regular file/);
});
test('source-only release includes deterministic source metadata and checksums', t => {
  const { files, plan, manifest } = prepared(t);
  assert.equal(files.size, 3); assert.equal(manifest.sourceCommit, plan.sourceCommit);
  assert.match(files.get('SHA256SUMS').toString(), new RegExp(sha256(files.get('release-plan.json'))));
});
test('publication stages all verified assets before publishing and retry writes nothing', t => {
  const item = prepared(t, ['server.tgz', 'frontend.tgz', 'provenance.json']);
  assert.equal(publishRelease(item.args).status, 'published');
  assert.equal(item.remote.mutations.at(-1), 'publish');
  assert.equal(item.remote.assets(1).length, item.files.size);
  const mutations = [...item.remote.mutations];
  assert.equal(publishRelease(item.args).status, 'already-published');
  assert.deepEqual(item.remote.mutations, mutations);
  assert.equal(item.remote.checked.sha, item.plan.sourceCommit);
});
test('missing artifact, changed bytes, wrong source and failed checks stop before mutation', t => {
  for (const mode of ['missing', 'changed', 'source', 'checks']) {
    const item = prepared(t, ['app.tgz']);
    if (mode === 'missing') rmSync(path.join(item.directory, 'app.tgz'));
    if (mode === 'changed') writeFileSync(path.join(item.directory, 'app.tgz'), 'changed');
    if (mode === 'source') item.args.expectedCommit = 'b'.repeat(40);
    if (mode === 'checks') item.remote.checksPass = false;
    assert.throws(() => publishRelease(item.args)); assert.deepEqual(item.remote.mutations, []);
  }
});
test('publication rejects uncommitted policy changes', t => {
  const item = prepared(t);
  item.config.streams.main.requiredChecks = ['different']; writeFileSync(path.join(item.cwd, 'release.json'), JSON.stringify(item.config));
  const changed = item.plan = makePlan({ cwd: item.cwd, repository: 'example/project' });
  item.args.plan = changed; item.args.manifest = artifactBundle(changed).manifest;
  assert.throws(() => publishRelease(item.args), /policy differs/); assert.deepEqual(item.remote.mutations, []);
});
test('interrupted upload resumes without replacing completed assets', t => {
  const item = prepared(t, ['app.tgz']); item.remote.uploadFailure = 'release-manifest.json';
  assert.throws(() => publishRelease(item.args), /Interrupted/);
  assert.equal(item.remote.getRelease(item.plan.tag).draft, true);
  const firstAssetId = item.remote.assets(1)[0].id;
  item.remote.uploadFailure = null; assert.equal(publishRelease(item.args).status, 'published');
  assert.equal(item.remote.assets(1)[0].id, firstAssetId);
  assert.equal(item.remote.mutations.filter(x => x === 'upload:app.tgz').length, 1);
});
test('concurrent identical tag, draft and upload creation converges', t => {
  const item = prepared(t); item.remote.raceTag = true; item.remote.raceDraft = true; item.remote.raceUpload = true;
  assert.equal(publishRelease(item.args).status, 'published');
});
test('conflicting tags and drafts are never repointed', t => {
  const item = prepared(t); item.remote.tags.set(item.plan.tag, 'c'.repeat(40));
  assert.throws(() => publishRelease(item.args), /conflicting release tag/); assert.deepEqual(item.remote.mutations, []);
  item.remote.tags.clear(); item.remote.releases.set(item.plan.tag, { tag_name: item.plan.tag, target_commitish: 'd'.repeat(40), body: 'another plan', draft: true });
  assert.throws(() => publishRelease(item.args), /different plan/); assert.deepEqual(item.remote.mutations, []);
});
test('conflicting assets and incomplete published releases are never repaired in place', t => {
  const item = prepared(t); publishRelease(item.args);
  const asset = [...item.remote.data.values()][0]; asset.bytes = Buffer.from('conflict');
  const mutations = [...item.remote.mutations]; assert.throws(() => publishRelease(item.args), /Conflicting remote asset/);
  assert.deepEqual(item.remote.mutations, mutations);
  item.remote.data.delete(asset.id); assert.throws(() => publishRelease(item.args), /missing expected assets/);
  assert.deepEqual(item.remote.mutations, mutations);
});
test('an incomplete baseline blocks a newer release', t => {
  const item = prepared(t); item.git('tag', item.plan.tag); item.commit('fix: newer change');
  const next = item.plan = makePlan({ cwd: item.cwd, repository: 'example/project' });
  item.args.plan = next; item.args.expectedCommit = next.sourceCommit; item.args.manifest = artifactBundle(next).manifest;
  assert.throws(() => publishRelease(item.args), /baseline release/); assert.deepEqual(item.remote.mutations, []);
});
test('GitHub check adapter rejects missing, pending and failed checks', () => {
  const github = new GitHub('example/project');
  let checks = []; let statuses = [];
  github.pages = endpoint => endpoint.includes('check-runs') ? checks : statuses;
  assert.throws(() => github.assertChecks('a'.repeat(40), ['check']), /missing/);
  checks = [{ name: 'check', status: 'in_progress', conclusion: null }];
  assert.throws(() => github.assertChecks('a'.repeat(40), ['check']), /not succeeded/);
  checks = [{ name: 'check', status: 'completed', conclusion: 'failure' }];
  assert.throws(() => github.assertChecks('a'.repeat(40), ['check']), /not succeeded/);
  checks[0].conclusion = 'success'; github.assertChecks('a'.repeat(40), ['check']);
  checks = []; statuses = [{ context: 'check', state: 'success' }]; github.assertChecks('a'.repeat(40), ['check']);
});

test('a recomputed digest cannot legitimize a version unrelated to source history', t => {
  const item = prepared(t);
  const { digest, ...content } = item.plan;
  content.version = '99.0.0'; content.tag = 'v99.0.0';
  const changed = { ...content, digest: sha256(jsonBytes(content)) };
  item.args.plan = changed; item.args.manifest = artifactBundle(changed).manifest;
  assert.throws(() => publishRelease(item.args), /source history/);
  assert.deepEqual(item.remote.mutations, []);
});
test('a locally fetched reservation tag does not break same-plan retry', t => {
  const item = prepared(t); item.git('tag', item.plan.tag);
  assert.equal(publishRelease(item.args).status, 'published');
});
test('GitHub adapter distinguishes missing resources from authorization failure', () => {
  const github = new GitHub('example/project');
  github.request = () => { throw Object.assign(new Error('unavailable'), { status: 403 }); };
  assert.throws(() => github.getTag('v1.0.0'), /unavailable/);
  github.request = () => { throw Object.assign(new Error('missing'), { status: 404 }); };
  assert.equal(github.getTag('v1.0.0'), null);
});
test('GitHub adapter resolves annotated tags and paginates releases', () => {
  const github = new GitHub('example/project');
  github.request = endpoint => {
    if (endpoint.includes('/git/ref/')) return { object: { type: 'tag', sha: 'tag-object' } };
    if (endpoint.includes('/git/tags/')) return { object: { type: 'commit', sha: 'e'.repeat(40) } };
    if (endpoint.endsWith('page=1')) return Array.from({length: 100}, (_, i) => ({tag_name: `v0.0.${i}`}));
    return [{tag_name: 'v1.0.0', draft: true}];
  };
  assert.equal(github.getTag('v1.0.0'), 'e'.repeat(40));
  assert.equal(github.getRelease('v1.0.0').draft, true);
});
test('CLI plan and verify interoperate without publication credentials', t => {
  const item = prepared(t, ['app.tgz']);
  const cli = path.resolve('release/cli.mjs');
  const env = { PATH: process.env.PATH };
  execFileSync(process.execPath, [cli, 'plan', '--repository', 'example/project'], { cwd: item.cwd, env });
  const output = execFileSync(process.execPath, [cli, 'verify', '--plan', 'build/release/release-plan.json', '--artifacts', item.directory], { cwd: item.cwd, env, encoding: 'utf8' });
  assert.match(output, /Verified 1 consumer artifacts/);
});

test('independent streams retain their own histories and version namespaces', t => {
  const repo = fixture(t, { tagPrefix: 'api-v', paths: ['api'] });
  repo.config.streams.web = { tagPrefix: 'web-v', initialVersion: '0.1.0', paths: ['web'], requiredChecks: ['check'] };
  writeFileSync(path.join(repo.cwd, 'release.json'), JSON.stringify(repo.config));
  repo.git('add', 'release.json'); repo.git('commit', '-m', 'chore: add stream');
  repo.git('tag', 'api-v1.2.0'); repo.git('tag', 'web-v4.5.0');
  for (const [directory, message] of [['api', 'fix: repair API'], ['web', 'feat: add page']]) {
    mkdirSync(path.join(repo.cwd, directory)); writeFileSync(path.join(repo.cwd, directory, 'source'), 'x');
    repo.git('add', directory); repo.git('commit', '-m', message);
  }
  assert.equal(repo.plan().tag, 'api-v1.2.1');
  assert.equal(makePlan({ cwd: repo.cwd, repository: 'example/project', stream: 'web' }).tag, 'web-v4.6.0');
});
test('a required check becoming unsuccessful during staging blocks publication', t => {
  const item = prepared(t); let checks = 0;
  item.remote.assertChecks = () => { if (++checks > 1) throw new Error('Check failed during upload'); };
  assert.throws(() => publishRelease(item.args), /failed during upload/);
  assert.equal(item.remote.getRelease(item.plan.tag).draft, true);
  assert.equal(item.remote.mutations.includes('publish'), false);
});
