import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

export class GitHub {
  constructor(repository) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) throw new Error('Invalid GitHub repository');
    this.repository = repository;
    this.base = `repos/${repository}`;
  }
  request(endpoint, { method = 'GET', data, binary = false, filename } = {}) {
    const args = ['api', endpoint, '--method', method, '-H', 'X-GitHub-Api-Version: 2022-11-28'];
    if (binary) args.push('-H', 'Accept: application/octet-stream');
    if (filename) args.push('-H', 'Content-Type: application/octet-stream', '--input', filename);
    else if (data !== undefined) args.push('--input', '-');
    try {
      const output = execFileSync('gh', args, { input: data === undefined ? undefined : JSON.stringify(data),
        maxBuffer: 512 * 1024 * 1024, stdio: ['pipe', 'pipe', 'pipe'] });
      return binary ? output : output.length ? JSON.parse(output.toString()) : null;
    } catch (error) {
      const message = error.stderr?.toString() ?? '';
      const failure = new Error(`GitHub ${method} request failed: ${message.trim() || error.message}`);
      failure.status = Number(message.match(/HTTP (\d{3})/)?.[1]) || null;
      throw failure;
    }
  }
  optional(endpoint) {
    try { return this.request(endpoint); }
    catch (error) { if (error.status === 404) return null; throw error; }
  }
  pages(endpoint, key) {
    const result = [];
    for (let page = 1; ; page++) {
      const response = this.request(`${endpoint}${endpoint.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
      const items = key ? response[key] : response;
      if (!Array.isArray(items)) throw new Error('Unexpected GitHub pagination response');
      result.push(...items);
      if (items.length < 100) return result;
    }
  }
  assertChecks(sha, names) {
    const checks = this.pages(`${this.base}/commits/${sha}/check-runs?filter=latest`, 'check_runs');
    const statuses = this.pages(`${this.base}/commits/${sha}/statuses`);
    for (const name of names) {
      const matching = checks.filter(check => check.name === name);
      if (matching.length) {
        if (matching.some(check => check.status !== 'completed' || check.conclusion !== 'success')) throw new Error(`Required check has not succeeded: ${name}`);
      } else {
        const status = statuses.find(item => item.context === name);
        if (status?.state !== 'success') throw new Error(`Required status is missing or has not succeeded: ${name}`);
      }
    }
  }
  getTag(tag) {
    const ref = this.optional(`${this.base}/git/ref/tags/${encodeURIComponent(tag)}`);
    if (!ref) return null;
    let object = ref.object;
    for (let depth = 0; object.type === 'tag' && depth < 10; depth++) object = this.request(`${this.base}/git/tags/${object.sha}`).object;
    if (object.type !== 'commit') throw new Error('Tag does not resolve to a commit');
    return object.sha;
  }
  createTag(tag, sha) { return this.request(`${this.base}/git/refs`, { method: 'POST', data: { ref: `refs/tags/${tag}`, sha } }); }
  getRelease(tag) {
    const matches = this.pages(`${this.base}/releases`).filter(release => release.tag_name === tag);
    if (matches.length > 1) throw new Error('Multiple releases use the requested tag');
    return matches[0] ?? null;
  }
  createDraft(plan, body) {
    return this.request(`${this.base}/releases`, { method: 'POST', data: {
      tag_name: plan.tag, target_commitish: plan.sourceCommit, name: plan.tag, body, draft: true, prerelease: false,
    } });
  }
  assets(id) { return this.pages(`${this.base}/releases/${id}/assets`); }
  download(id) { return this.request(`${this.base}/releases/assets/${id}`, { binary: true }); }
  upload(id, name, bytes) {
    const directory = mkdtempSync(path.join(tmpdir(), 'delivery-upload-'));
    try {
      const filename = path.join(directory, 'asset');
      writeFileSync(filename, bytes, { mode: 0o600 });
      return this.request(`https://uploads.github.com/${this.base}/releases/${id}/assets?name=${encodeURIComponent(name)}`,
        { method: 'POST', filename });
    } finally { rmSync(directory, { recursive: true, force: true }); }
  }
  publish(id) { return this.request(`${this.base}/releases/${id}`, { method: 'PATCH', data: { draft: false } }); }
}
