import test from 'node:test';
import assert from 'node:assert/strict';
import { researchPlan, PORTS } from '../scripts/run_research.mjs';

test('integrated startup includes the existing assistant, dashboard and isolated terminal only', () => {
  const plan = researchPlan({PATH:'/bin'}, 'linux');
  assert.equal(plan.length, 3);
  assert.deepEqual(PORTS, [8011, 5173, 3001, 4001]);
  assert.deepEqual(plan[0].args, ['-m', 'api.advisor']);
  assert(plan[1].args.includes('--strictPort'));
  assert(plan[2].args[0].endsWith('scripts/openterminal.mjs'));
});

test('startup does not inherit tokens, broker keys, Node hooks or live environment', () => {
  const plan = researchPlan({PATH:'/bin',ADVISORY_ACCESS_TOKEN:'synthetic',API_KEY:'synthetic',BINANCE_SECRET:'synthetic',NODE_OPTIONS:'--inspect',ENVIRONMENT:'live',OPERATING_PROFILE:'general',ADVISORY_KAFKA_SERVERS:'synthetic',ENABLE_DEFI_AGENTS:'true'});
  for (const child of plan) {
    for (const key of ['ADVISORY_ACCESS_TOKEN','API_KEY','BINANCE_SECRET','NODE_OPTIONS']) assert.equal(child.env[key], undefined);
  }
  assert.equal(plan[0].env.ENVIRONMENT, 'development');
  assert.equal(plan[0].env.OPERATING_PROFILE, 'earn2trade_tcp50');
  assert.equal(plan[0].env.ENABLE_DEFI_AGENTS, 'false');
  assert.equal(plan[0].env.ADVISORY_KAFKA_SERVERS, '');
});

test('Windows plan uses the correct Python path and npm executable', () => {
  const plan = researchPlan({}, 'win32');
  assert(plan[0].command.replaceAll('\\','/').endsWith('.venv/Scripts/python.exe'));
  assert.equal(plan[1].command, 'npm.cmd');
  assert.equal(plan[1].shell, true);
  assert.equal(plan[2].shell, false);
});
