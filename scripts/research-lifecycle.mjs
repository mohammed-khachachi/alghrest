/** Lifecycle metadata only: never include environment, argv, or raw child output. */
export function lifecycleLogger(launcher) {
  return (event, {
    service = null, child_pid = null, reason = null, signal = null, code = null,
    sender = 'unknown', sender_pid = null, error_code = null,
  } = {}) => {
    console.error(`[research-lifecycle] ${JSON.stringify({
      timestamp: new Date().toISOString(), launcher, launcher_pid: process.pid,
      launcher_ppid: process.ppid, event, service, child_pid, reason, signal, code,
      sender, sender_pid, error_code,
    })}`);
  };
}

export function exitDescription(code, signal) {
  return signal ? `signal ${signal}; code ${code}` : `code ${code}`;
}
