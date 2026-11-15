import { artifactBundle, assertManifest, assertSource, sha256 } from './core.mjs';

function verifyRemoteAssets(remote, release, files, complete) {
  const assets = remote.assets(release.id);
  const seen = new Set();
  for (const asset of assets) {
    if (seen.has(asset.name) || !files.has(asset.name)) throw new Error(`Unexpected or duplicate remote asset: ${asset.name}`);
    seen.add(asset.name);
    const expected = files.get(asset.name);
    if (asset.state !== 'uploaded' || asset.size !== expected.length || sha256(remote.download(asset.id)) !== sha256(expected)) {
      throw new Error(`Conflicting remote asset: ${asset.name}`);
    }
  }
  if (complete && seen.size !== files.size) throw new Error('Published release is missing expected assets');
  return seen;
}

export function publishRelease({ plan, manifest, directory, cwd = '.', expectedCommit, remote }) {
  // All local verification and exact-source checks precede any remote mutation.
  assertSource(plan, cwd, expectedCommit);
  if (remote.repository !== plan.repository) throw new Error('Publisher repository differs from release plan');
  const { manifest: actual, files } = artifactBundle(plan, directory);
  assertManifest(manifest, actual);
  remote.assertChecks(plan.sourceCommit, plan.policy.requiredChecks);
  if (plan.baselineTag) {
    const baseline = remote.getRelease(plan.baselineTag);
    if (!baseline || baseline.draft) throw new Error('Finish publishing the baseline release before advancing this stream');
  }
  const body = `${plan.notes}\n<!-- delivery-tooling-plan:${plan.digest} -->\n`;
  let release = remote.getRelease(plan.tag);
  const assertMatching = () => {
    if (release.tag_name !== plan.tag || release.target_commitish !== plan.sourceCommit || release.body !== body) {
      throw new Error('Existing release belongs to a different plan; retain and retry its original plan');
    }
  };
  if (release) {
    assertMatching();
    verifyRemoteAssets(remote, release, files, !release.draft);
  }
  let tagCommit = remote.getTag(plan.tag);
  if (release && !release.draft && !tagCommit) throw new Error('Published release tag is missing; refusing to recreate it');
  if (!tagCommit) {
    try { remote.createTag(plan.tag, plan.sourceCommit); }
    catch (error) {
      if (remote.getTag(plan.tag) !== plan.sourceCommit) throw error;
    }
    tagCommit = remote.getTag(plan.tag);
  }
  if (tagCommit !== plan.sourceCommit) throw new Error('Refusing to move a conflicting release tag');
  if (!release) {
    try { release = remote.createDraft(plan, body); }
    catch (error) { release = remote.getRelease(plan.tag); if (!release) throw error; }
  }
  assertMatching();
  const present = verifyRemoteAssets(remote, release, files, !release.draft);
  if (!release.draft) return { status: 'already-published', url: release.html_url };
  for (const [name, bytes] of files) {
    if (present.has(name)) continue;
    try { remote.upload(release.id, name, bytes); }
    catch (error) {
      // A concurrent matching run may have completed this exact upload.
      if (!verifyRemoteAssets(remote, release, files, false).has(name)) throw error;
    }
  }
  verifyRemoteAssets(remote, release, files, true);
  if (remote.getTag(plan.tag) !== plan.sourceCommit) throw new Error('Release tag changed during publication');
  remote.assertChecks(plan.sourceCommit, plan.policy.requiredChecks);
  const published = remote.publish(release.id);
  if (published.draft) throw new Error('GitHub did not publish the release');
  return { status: 'published', url: published.html_url };
}
