import { useLanguage, tr } from "../i18n";
import { useDashboardStore } from '@/store/useStore';
import { Skeleton } from '@/components/common/Skeleton';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { MiniSparkline } from '@/components/charts/MiniSparkline';
import { KafkaFlowDiagram } from '@/components/kafka/KafkaFlowDiagram';
import { KAFKA_TOPICS, type KafkaTopicMetrics } from '@/types/ws';
import { clsx } from 'clsx';
import { useRef, useEffect, useState } from 'react';

interface TopicCardProps {
  topic: KafkaTopicMetrics;
}

function usePulse(value: number): boolean {
  const prevRef = useRef(value);
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    if (value !== prevRef.current) {
      prevRef.current = value;
      setPulse(true);
      const t = setTimeout(() => setPulse(false), 600);
      return () => clearTimeout(t);
    }
  }, [value]);

  return pulse;
}

function TopicCard({ topic }: TopicCardProps) {
  useLanguage();
  const pulsing = usePulse(topic.total_messages);
  const lagOk = topic.consumer_lag_ms < 500;
  const lagWarn = topic.consumer_lag_ms >= 500 && topic.consumer_lag_ms < 1000;

  // Build fake sparkline data from messages_per_sec
  const sparkData = Array.from({ length: 20 }, () =>
    Math.max(0, topic.messages_per_sec + (Math.random() - 0.5) * topic.messages_per_sec * 0.4),
  );

  return (
    <div
      className={clsx(
        'bg-bg-surface border rounded-xl p-4 transition-all duration-300',
        pulsing
          ? 'border-indigo-500/60 shadow-[0_0_12px_rgba(99,102,241,0.3)]'
          : 'border-white/8',
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <h3
          className="font-mono text-xs font-semibold text-white truncate"
          title={tr(topic.name)}
        >
          {topic.name}
        </h3>
        {pulsing && (
          <span className="flex-shrink-0 w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs mb-3">
        <div>
          <div className="text-text-muted">{tr("msg/s")}</div>
          <div className="font-mono font-bold text-white">
            {tr(topic.messages_per_sec.toFixed(1))}
          </div>
        </div>
        <div>
          <div className="text-text-muted">{tr("lag")}</div>
          <div
            className={clsx(
              'font-mono font-bold',
              lagOk && 'text-green-400',
              lagWarn && 'text-amber-400',
              !lagOk && !lagWarn && 'text-red-400',
            )}
          >
            {tr(topic.consumer_lag_ms)}{tr("ms")}</div>
        </div>
        <div>
          <div className="text-text-muted">{tr("total")}</div>
          <div className="font-mono text-slate-300">
            {tr(topic.total_messages.toLocaleString())}
          </div>
        </div>
        <div>
          <div className="text-text-muted">{tr("partitions")}</div>
          <div className="font-mono text-slate-300">{tr(topic.partition_count)}</div>
        </div>
      </div>

      <MiniSparkline data={sparkData} color="#6366f1" height={28} />

      <div className="mt-2 text-xs text-text-muted font-mono truncate">
        {tr(new Date(topic.last_message_ts).toLocaleTimeString('en-US', { hour12: false }))}
      </div>
    </div>
  );
}

function TopicCardSkeleton() {
  useLanguage();
  return (
    <div className="bg-bg-surface border border-white/8 rounded-xl p-4 space-y-3">
      <Skeleton className="h-3 w-3/4 rounded" />
      <Skeleton className="h-8 rounded" />
      <Skeleton className="h-6 rounded" />
    </div>
  );
}

export function Kafka() {
  useLanguage();
  const kafkaTopics = useDashboardStore((s) => s.kafkaTopics);

  const topicMap = new Map(kafkaTopics.map((t) => [t.name, t]));

  return (
    <div className="p-6 space-y-6">
      {/* Topic grid */}
      <ErrorBoundary>
        <div>
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">{tr("Topic Metrics — 16 Topics")}</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
            {kafkaTopics.length === 0
              ? Array.from({ length: 16 }).map((_, i) => (
                  <TopicCardSkeleton key={i} />
                ))
              : KAFKA_TOPICS.map((name) => {
                  const topic = topicMap.get(name);
                  if (!topic) {
                    return (
                      <div
                        key={name}
                        className="bg-bg-surface border border-white/8 rounded-xl p-4 opacity-40"
                      >
                        <div className="font-mono text-xs text-text-muted">{tr(name)}</div>
                        <div className="text-xs text-text-muted mt-1">{tr("No data")}</div>
                      </div>
                    );
                  }
                  return <TopicCard key={name} topic={topic} />;
                })}
          </div>
        </div>
      </ErrorBoundary>

      {/* Flow diagram */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl p-6">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-6">{tr("Message Flow — Tier Topology")}</h2>
          <KafkaFlowDiagram />
        </div>
      </ErrorBoundary>
    </div>
  );
}
