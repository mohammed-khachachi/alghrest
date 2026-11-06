// Opt-in host integration: creates only uniquely named, short-lived fixture services.
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {serviceArguments} from '../scripts/openterminal-service.mjs';
const run = (command, args) => execFileSync(command, args, {encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']});
const wait = ms => new Promise(accept => setTimeout(accept, ms));
async function until(check, timeout = 16000) {
  const deadline = Date.now() + timeout;
  do { if (check()) return; await wait(200); } while (Date.now() < deadline);
  throw new Error('Fixture condition did not become true.');
}
test('user service persists beyond launch command, recovers, stops and rate-limits crashes',
  {skip: process.env.OPENTERMINAL_SYSTEMD_FIXTURE !== '1', timeout: 45000}, async () => {
    const unit = `alghrest-openterminal-fixture-${process.pid}.service`;
    const status = () => Object.fromEntries(run('/usr/bin/systemctl', ['--user', 'show', unit,
      '-p', 'ActiveState', '-p', 'NRestarts', '-p', 'MainPID', '-p', 'ControlGroup', '-p', 'Result'])
      .trim().split('\n').map(line => line.split('=')));
    function start(code) {
      const args = serviceArguments().map(arg => arg.startsWith('--unit=') ? `--unit=${unit}` : arg);
      args.splice(-1, 1, '-e', code);
      run('/usr/bin/systemd-run', args);
    }
    try {
      start('setInterval(() => {}, 1000)');
      await until(() => status().ActiveState === 'active');
      const initial = status();
      assert.ok(initial.ControlGroup.endsWith(`/${unit}`));
      assert.ok(!initial.ControlGroup.includes('chromium'));
      await wait(1200);
      assert.equal(status().MainPID, initial.MainPID); // launcher command already exited
      run('/usr/bin/systemctl', ['--user', 'kill', '--signal=TERM', '--kill-whom=main', unit]);
      await until(() => status().ActiveState === 'active' && status().NRestarts === '1');
      assert.notEqual(status().MainPID, initial.MainPID);
      run('/usr/bin/systemctl', ['--user', 'stop', unit]);
      await wait(3500);
      assert.notEqual(status().ActiveState, 'active');
      start('process.exit(1)');
      await until(() => status().ActiveState === 'failed' && status().NRestarts === '3');
      const limited = status();
      assert.equal(limited.MainPID, '0');
      const journal = run('/usr/bin/journalctl', ['--user', `--unit=${unit}`, '--no-pager', '-n', '50', '-o', 'cat']);
      assert.match(journal, /Start request repeated too quickly/);
      await wait(6500);
      assert.deepEqual(status(), limited);
    } finally {
      try {run('/usr/bin/systemctl', ['--user', 'stop', unit]);} catch {}
      try {run('/usr/bin/systemctl', ['--user', 'reset-failed', unit]);} catch {}
    }
  });
