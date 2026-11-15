import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync, lstatSync, readdirSync, realpathSync } from 'node:fs';
import path from 'node:path';
import Ajv from 'ajv';
import semver from 'semver';
import { CommitParser } from 'conventional-commits-parser';

export const sha256 = data => createHash('sha256').update(data).digest('hex');
export function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])]));
  return value;
}
export const jsonBytes = value => Buffer.from(JSON.stringify(stable(value), null, 2) + '\n');
const digest = value => sha256(jsonBytes(value));
const ajv = new Ajv({ allErrors: true, useDefaults: true });
const configSchema = JSON.parse(readFileSync(new URL('../schemas/release.schema.json', import.meta.url)));
ajv.addSchema(configSchema);
const validateConfig = ajv.getSchema(configSchema.$id);
const validatePlanSchema = ajv.compile(JSON.parse(readFileSync(new URL('../schemas/release-plan.schema.json', import.meta.url))));
const reserved = ['release-plan.json', 'release-manifest.json', 'SHA256SUMS'];
export function git(cwd, ...args) {
  return execFileSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }).trimEnd();
}
export function configFrom(text) {
  const config = JSON.parse(text);
  if (!validateConfig(config)) throw new Error(`Invalid release config: ${ajv.errorsText(validateConfig.errors)}`);
  const prefixes = new Set();
  for (const policy of Object.values(config.streams)) {
    for (const prefix of [policy.tagPrefix, ...policy.legacyTagPrefixes]) {
      if (prefixes.has(prefix)) throw new Error(`Release streams share tag prefix: ${prefix}`);
      prefixes.add(prefix);
      execFileSync('git', ['check-ref-format', `refs/tags/${prefix}0.0.0`], { stdio: 'pipe' });
    }
    if (policy.artifacts.some(name => reserved.includes(name))) throw new Error('Artifact uses reserved release metadata name');
  }
  return config;
}
const parser = new CommitParser({
  headerPattern: /^(\w+)(?:\(([^)]+)\))?(!)?: (.+)$/,
  headerCorrespondence: ['type', 'scope', 'breaking', 'subject'],
  noteKeywords: ['BREAKING CHANGE', 'BREAKING-CHANGE'],
});
export function bumpFor(messages) {
  let bump = null;
  for (const message of messages) {
    const commit = parser.parse(message);
    if (commit.breaking || commit.notes.length) return 'major';
    if (commit.type === 'feat') bump = 'minor';
    else if (['fix', 'perf'].includes(commit.type) && bump !== 'minor') bump = 'patch';
  }
  return bump;
}
export function makePlan({ cwd = '.', configPath = 'release.json', stream = 'main', repository, ref = 'HEAD', configText, excludeTag }) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository ?? '')) throw new Error('repository must be owner/name');
  if (git(cwd, 'rev-parse', '--is-shallow-repository') === 'true') throw new Error('Release planning requires complete history and tags');
  if (path.isAbsolute(configPath) || configPath.split(/[\\/]/).includes('..')) throw new Error('Config path must be relative to the repository root');
  const config = configFrom(configText ?? readFileSync(path.join(cwd, configPath), 'utf8'));
  const policy = config.streams[stream];
  if (!policy) throw new Error(`Unknown release stream: ${stream}`);
  const sourceCommit = git(cwd, 'rev-parse', '--verify', '--end-of-options', `${ref}^{commit}`);
  const tags = git(cwd, 'tag', '--merged', sourceCommit).split('\n').filter(tag => tag && tag !== excludeTag);
  const prefixes = [policy.tagPrefix, ...policy.legacyTagPrefixes];
  const releases = tags.flatMap(tag => prefixes.flatMap(prefix => {
    const version = tag.startsWith(prefix) ? tag.slice(prefix.length) : '';
    return semver.valid(version) === version && !semver.prerelease(version) && !version.includes('+') ? [{ tag, version }] : [];
  })).sort((a, b) => semver.rcompare(a.version, b.version) || a.tag.localeCompare(b.tag));
  const baseline = releases[0];
  const range = baseline ? `${baseline.tag}..${sourceCommit}` : sourceCommit;
  const shas = git(cwd, 'log', '--reverse', '--format=%H', range, '--', ...policy.paths).split('\n').filter(Boolean);
  const messages = shas.map(sha => git(cwd, 'show', '-s', '--format=%B', sha));
  const bump = bumpFor(messages);
  const version = !bump ? null : baseline ? semver.inc(baseline.version, bump)
    : bump === 'major' && semver.major(policy.initialVersion) === 0 ? '1.0.0' : policy.initialVersion;
  const tag = version ? policy.tagPrefix + version : null;
  const notes = version ? `# ${tag}\n\n` + messages.map((message, i) => {
    const [subject, ...body] = message.split('\n');
    return `- ${subject} (${shas[i].slice(0, 12)})\n` + (body.join('\n').trim() ? '\n' + body.map(line => `  ${line}`).join('\n') + '\n' : '');
  }).join('\n') : '';
  const plan = { schemaVersion: 1, repository, stream, policy, sourceCommit, configPath,
    configDigest: digest(config), baselineTag: baseline?.tag ?? null, release: Boolean(bump), version, tag, bump, notes };
  plan.digest = digest(plan);
  return assertPlan(plan);
}
export function assertPlan(plan) {
  if (!validatePlanSchema(plan)) throw new Error(`Invalid release plan: ${ajv.errorsText(validatePlanSchema.errors)}`);
  const { digest: claimed, ...content } = plan;
  if (digest(content) !== claimed) throw new Error('Release plan digest mismatch');
  if (plan.release ? (!plan.bump || !plan.version || plan.tag !== plan.policy.tagPrefix + plan.version)
    : (plan.bump !== null || plan.version !== null || plan.tag !== null)) throw new Error('Inconsistent release plan');
  return plan;
}
export function assertSource(plan, cwd, expectedCommit) {
  assertPlan(plan);
  if (expectedCommit !== plan.sourceCommit || git(cwd, 'rev-parse', 'HEAD') !== plan.sourceCommit) throw new Error('Checkout and expected commit must match the release plan');
  const configText = git(cwd, 'show', `${plan.sourceCommit}:${plan.configPath}`);
  const committed = configFrom(configText);
  if (digest(committed) !== plan.configDigest || digest(committed.streams[plan.stream]) !== digest(plan.policy)) throw new Error('Release policy differs from the source commit');
  // A retry may have already reserved this tag. Recompute against its original
  // history without treating that reservation as a newly completed baseline.
  const expected = makePlan({ cwd, configPath: plan.configPath, stream: plan.stream,
    repository: plan.repository, ref: plan.sourceCommit, configText, excludeTag: plan.tag });
  if (expected.digest !== plan.digest) throw new Error('Release plan differs from source history');
}
export function artifactBundle(plan, directory) {
  assertPlan(plan);
  if (!plan.release) throw new Error('There is no release to verify');
  const expected = [...plan.policy.artifacts].sort();
  const files = new Map();
  if (directory) {
    if (lstatSync(directory).isSymbolicLink() || !lstatSync(directory).isDirectory()) throw new Error('Artifact root must be a real directory');
    const actual = readdirSync(directory).sort();
    if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error('Artifact directory does not contain the exact expected set');
    for (const name of expected) {
      const filename = path.join(directory, name);
      const stat = lstatSync(filename);
      if (!stat.isFile() || stat.isSymbolicLink() || path.dirname(realpathSync(filename)) !== realpathSync(directory)) throw new Error(`Artifact must be a regular file: ${name}`);
      files.set(name, readFileSync(filename));
    }
  } else if (expected.length) throw new Error('Artifact directory is required for this stream');
  const assets = [...files].map(([name, data]) => ({ name, size: data.length, sha256: sha256(data) }));
  const manifest = { schemaVersion: 1, repository: plan.repository, stream: plan.stream,
    sourceCommit: plan.sourceCommit, version: plan.version, tag: plan.tag, planDigest: plan.digest, assets };
  files.set('release-plan.json', jsonBytes(plan));
  files.set('release-manifest.json', jsonBytes(manifest));
  files.set('SHA256SUMS', Buffer.from([...files].sort(([a], [b]) => a.localeCompare(b)).map(([name, bytes]) => `${sha256(bytes)}  ${name}\n`).join('')));
  return { manifest, files };
}
export function assertManifest(actual, expected) {
  if (digest(actual) !== digest(expected)) throw new Error('Artifacts differ from the verified manifest');
}
