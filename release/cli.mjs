#!/usr/bin/env node
import { parseArgs } from 'node:util';
import { readFileSync, writeFileSync, mkdirSync, appendFileSync } from 'node:fs';
import path from 'node:path';
import { makePlan, assertPlan, artifactBundle, jsonBytes } from './core.mjs';
import { publishRelease } from './publish.mjs';
import { GitHub } from './github.mjs';

const help = `Usage:
  node release/cli.mjs plan --repository owner/name [--config release.json] [--stream main] [--ref HEAD] [--output build/release]
  node release/cli.mjs verify --plan FILE [--artifacts DIR] [--output build/release]
  node release/cli.mjs publish --plan FILE --manifest FILE --expected-commit SHA [--artifacts DIR]

Run in the consumer repository. Plan and verify never contact GitHub. Publish
requires gh, a GitHub token, an exact-source checkout and successful required
checks. Preserve the original plan and artifacts to retry interrupted publication.
`;
try {
  const { positionals, values } = parseArgs({ allowPositionals: true, options: Object.fromEntries([
    'repository', 'config', 'stream', 'ref', 'output', 'plan', 'artifacts', 'manifest', 'expected-commit',
  ].map(name => [name, { type: 'string' }]).concat([['help', { type: 'boolean' }]])) });
  if (values.help) { console.log(help); process.exit(0); }
  const command = positionals[0];
  if (positionals.length !== 1 || !['plan', 'verify', 'publish'].includes(command)) throw new Error(help);
  const output = values.output ?? 'build/release';
  if (command === 'plan') {
    const plan = makePlan({ repository: values.repository, configPath: values.config, stream: values.stream, ref: values.ref });
    mkdirSync(output, { recursive: true });
    const filename = path.join(output, 'release-plan.json');
    writeFileSync(filename, jsonBytes(plan));
    writeFileSync(path.join(output, 'notes.md'), plan.notes);
    console.log(JSON.stringify({ release: plan.release, version: plan.version, tag: plan.tag, sourceCommit: plan.sourceCommit, plan: filename }, null, 2));
    if (process.env.GITHUB_OUTPUT) {
      const outputs = { release: String(plan.release), version: plan.version ?? '', tag: plan.tag ?? '', 'source-commit': plan.sourceCommit, plan: filename };
      for (const [key, value] of Object.entries(outputs)) {
        if (/[\r\n]/.test(value)) throw new Error('Output contains an invalid newline');
        appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${value}\n`);
      }
    }
  } else {
    if (!values.plan) throw new Error('--plan is required');
    const plan = assertPlan(JSON.parse(readFileSync(values.plan, 'utf8')));
    if (command === 'verify') {
      if (values.artifacts && path.resolve(values.artifacts) === path.resolve(output)) throw new Error('Manifest output must be separate from the artifact directory');
      const bundle = artifactBundle(plan, values.artifacts);
      mkdirSync(output, { recursive: true });
      for (const name of ['release-plan.json', 'release-manifest.json', 'SHA256SUMS']) writeFileSync(path.join(output, name), bundle.files.get(name));
      console.log(`Verified ${bundle.manifest.assets.length} consumer artifacts for ${plan.tag}`);
    } else {
      if (!values.manifest || !values['expected-commit']) throw new Error('--manifest and --expected-commit are required');
      const manifest = JSON.parse(readFileSync(values.manifest, 'utf8'));
      console.log(JSON.stringify(publishRelease({ plan, manifest, directory: values.artifacts,
        expectedCommit: values['expected-commit'], remote: new GitHub(plan.repository) }), null, 2));
    }
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
