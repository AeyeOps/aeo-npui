import { StatusBar } from 'expo-status-bar';
import {
  ActivityIndicator,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import { useEffect, useMemo, useRef, useState } from 'react';

type ViewMode = 'split' | 'chat' | 'metrics' | 'log';

type Message = {
  role: 'user' | 'assistant';
  content: string;
};

type Trend = {
  label: string;
  unit: string;
  values: number[];
  current: number;
  peak: number;
};

type ArtifactRow = {
  label: string;
  value: string;
};

type DashboardState = {
  title: string;
  mode: string;
  status: string;
  activeModel: string;
  activeRunId: string;
  selectedCommand: string;
  notes: string[];
  interactionLines: string[];
  trends: Trend[];
  artifactRows: ArtifactRow[];
};

type EnduranceSummary = {
  command: string;
  requested_runs: number;
  completed_runs: number;
  passed_runs: number;
  failed_runs: number;
  mean_duration_seconds: number;
  peak_npu_util_percent: number;
};

type ConsoleState = {
  statusLine: string;
  helpLine: string;
  systemMessage: string | null;
  startupState: 'starting' | 'ready' | 'failed' | 'idle';
  sessionRunId: string | null;
  messages: Message[];
  controls: string[];
  dashboard: DashboardState;
  logLines: string[];
  endurance: EnduranceSummary | null;
};

const API_BASE_URL = process.env.EXPO_PUBLIC_NPU_API_BASE_URL ?? 'http://127.0.0.1:8765';
const POLL_INTERVAL_MS = 1200;

function sparkline(values: number[]): string {
  const bars = '▁▂▃▄▅▆▇█';
  if (!values.length) {
    return '';
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return bars[0].repeat(values.length);
  }
  return values
    .map((value) => {
      const normalized = (value - min) / (max - min);
      const index = Math.min(bars.length - 1, Math.round(normalized * (bars.length - 1)));
      return bars[index];
    })
    .join('');
}

function shorten(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `...${value.slice(-(maxLength - 3))}`;
}

async function fetchState(): Promise<ConsoleState> {
  const response = await fetch(`${API_BASE_URL}/api/state`);
  if (!response.ok) {
    throw new Error(`State request failed: ${response.status}`);
  }
  return (await response.json()) as ConsoleState;
}

async function postJson(path: string, body?: object): Promise<ConsoleState> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`POST ${path} failed: ${response.status}`);
  }
  return (await response.json()) as ConsoleState;
}

export default function App() {
  const { width } = useWindowDimensions();
  const [state, setState] = useState<ConsoleState | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('split');
  const [composer, setComposer] = useState('');
  const [followLog, setFollowLog] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const logScrollRef = useRef<ScrollView>(null);
  const isWide = width >= 1180;

  const loadState = async () => {
    try {
      const next = await fetchState();
      setState(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load console state');
    }
  };

  useEffect(() => {
    void loadState();
    const interval = setInterval(() => {
      void loadState();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (followLog && viewMode === 'log' && logScrollRef.current) {
      logScrollRef.current.scrollToEnd({ animated: true });
    }
  }, [followLog, viewMode, state?.logLines.length]);

  const statusTone = useMemo(() => {
    switch (state?.startupState) {
      case 'ready':
        return styles.statusReady;
      case 'failed':
        return styles.statusFailed;
      case 'starting':
        return styles.statusStarting;
      default:
        return styles.statusIdle;
    }
  }, [state?.startupState]);

  const submitComposer = async () => {
    const text = composer.trim();
    if (!text) {
      return;
    }
    setSubmitting(true);
    try {
      if (text === '/clear') {
        setState(await postJson('/api/chat/clear'));
      } else if (text === '/quit') {
        setState(await postJson('/api/session/stop'));
      } else if (text.startsWith('/view ')) {
        const selected = text.replace('/view ', '').trim();
        if (selected === 'split' || selected === 'chat' || selected === 'metrics' || selected === 'log') {
          setViewMode(selected);
        }
      } else {
        setState(await postJson('/api/chat/send', { text }));
      }
      setComposer('');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit input');
    } finally {
      setSubmitting(false);
    }
  };

  const renderMainPane = () => {
    if (!state) {
      return (
        <View style={styles.loadingPanel}>
          <ActivityIndicator size="large" color="#49dcb1" />
          <Text style={styles.loadingTitle}>Booting local NPU console</Text>
          <Text style={styles.loadingCopy}>Waiting for the browser API to come online.</Text>
        </View>
      );
    }

    if (viewMode === 'metrics') {
      return (
        <ScrollView style={styles.panelSurface} contentContainerStyle={styles.panelContent}>
          <SectionTitle label="Metrics" eyebrow="Live signal" />
          {state.dashboard.trends.map((trend) => (
            <View key={trend.label} style={styles.metricBlock}>
              <View style={styles.metricHeader}>
                <Text style={styles.metricLabel}>{trend.label}</Text>
                <Text style={styles.metricValue}>
                  {trend.current.toFixed(0)}
                  {trend.unit} / {trend.peak.toFixed(0)}
                  {trend.unit}
                </Text>
              </View>
              <Text style={styles.sparkline}>{sparkline(trend.values)}</Text>
            </View>
          ))}
          <SectionTitle label="Artifacts" eyebrow="Current run" />
          {state.dashboard.artifactRows.map((row) => (
            <View key={row.label} style={styles.artifactRow}>
              <Text style={styles.artifactLabel}>{row.label}</Text>
              <Text style={styles.artifactValue}>{row.value}</Text>
            </View>
          ))}
        </ScrollView>
      );
    }

    if (viewMode === 'log') {
      return (
        <View style={styles.panelSurface}>
          <View style={styles.panelHeaderRow}>
            <SectionTitle label="Run Log" eyebrow={followLog ? 'Follow on' : 'Follow paused'} />
            <Pressable style={styles.ghostButton} onPress={() => setFollowLog((value) => !value)}>
              <Text style={styles.ghostButtonLabel}>{followLog ? 'Pause follow' : 'Resume follow'}</Text>
            </Pressable>
          </View>
          <ScrollView
            ref={logScrollRef}
            style={styles.logScroll}
            contentContainerStyle={styles.logContent}
            onScrollBeginDrag={() => setFollowLog(false)}
          >
            {(state.logLines.length ? state.logLines : ['No log entries yet.']).map((line, index) => (
              <Text key={`${index}-${line}`} style={styles.logLine}>
                {line}
              </Text>
            ))}
          </ScrollView>
        </View>
      );
    }

    return (
      <View style={styles.panelSurface}>
        <View style={styles.panelHeaderRow}>
          <SectionTitle label="Chat with local NPU" eyebrow="Persistent session" />
          <View style={styles.modePill}>
            <Text style={styles.modePillLabel}>{state.dashboard.mode}</Text>
          </View>
        </View>
        <ScrollView style={styles.transcriptScroll} contentContainerStyle={styles.transcriptContent}>
          {state.messages.length === 0 ? (
            <Text style={styles.emptyCopy}>No conversation yet. Send a prompt to warm up the NPU session.</Text>
          ) : null}
          {state.messages.map((message, index) => (
            <View
              key={`${message.role}-${index}`}
              style={[
                styles.messageBubble,
                message.role === 'user' ? styles.userBubble : styles.assistantBubble,
              ]}
            >
              <Text style={styles.messageRole}>{message.role === 'user' ? 'You' : 'NPU'}</Text>
              <Text style={styles.messageText}>{message.content}</Text>
            </View>
          ))}
          {state.systemMessage ? (
            <View style={styles.systemBanner}>
              <Text style={styles.systemBannerLabel}>System</Text>
              <Text style={styles.systemBannerText}>{state.systemMessage}</Text>
            </View>
          ) : null}
        </ScrollView>
      </View>
    );
  };

  const renderSidePane = () => {
    if (!state) {
      return null;
    }

    return (
      <View style={styles.sideColumn}>
        <View style={styles.infoCard}>
          <SectionTitle label="Now" eyebrow="Session" compact />
          <InfoRow label="Status" value={state.statusLine} />
          <InfoRow label="Prompt" value={state.helpLine} />
          <InfoRow label="Model" value={shorten(state.dashboard.activeModel, 48)} />
          <InfoRow label="Run ID" value={state.dashboard.activeRunId} />
          <InfoRow label="Command" value={state.dashboard.selectedCommand} />
        </View>

        <View style={styles.infoCard}>
          <SectionTitle label="Signals" eyebrow="Live metrics" compact />
          {state.dashboard.trends.slice(0, 4).map((trend) => (
            <View key={trend.label} style={styles.signalRow}>
              <View>
                <Text style={styles.signalLabel}>{trend.label}</Text>
                <Text style={styles.signalMetric}>
                  {trend.current.toFixed(0)}
                  {trend.unit} / {trend.peak.toFixed(0)}
                  {trend.unit}
                </Text>
              </View>
              <Text style={styles.signalSpark}>{sparkline(trend.values.slice(-24))}</Text>
            </View>
          ))}
        </View>

        <View style={styles.infoCard}>
          <SectionTitle label="Operator Notes" eyebrow="Golden path" compact />
          {state.dashboard.notes.map((note) => (
            <Text key={note} style={styles.noteLine}>
              • {note}
            </Text>
          ))}
        </View>

        {state.endurance ? (
          <View style={styles.infoCard}>
            <SectionTitle label="Endurance" eyebrow="Latest run" compact />
            <InfoRow label="Command" value={state.endurance.command} />
            <InfoRow
              label="Pass / fail"
              value={`${state.endurance.passed_runs} / ${state.endurance.failed_runs}`}
            />
            <InfoRow
              label="Completed"
              value={`${state.endurance.completed_runs} / ${state.endurance.requested_runs}`}
            />
            <InfoRow
              label="Mean seconds"
              value={state.endurance.mean_duration_seconds.toFixed(3)}
            />
            <InfoRow
              label="Peak NPU"
              value={`${state.endurance.peak_npu_util_percent.toFixed(1)}%`}
            />
          </View>
        ) : null}
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="light" />
      <View style={styles.appShell}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.overline}>NPU console</Text>
            <Text style={styles.title}>Local chat, metrics, and operator log without the TUI</Text>
          </View>
          <View style={[styles.statusChip, statusTone]}>
            <Text style={styles.statusChipLabel}>{state?.startupState ?? 'loading'}</Text>
          </View>
        </View>

        <View style={styles.toolbar}>
          {(['split', 'chat', 'metrics', 'log'] as ViewMode[]).map((mode) => (
            <Pressable
              key={mode}
              style={[styles.toolbarButton, viewMode === mode ? styles.toolbarButtonActive : null]}
              onPress={() => setViewMode(mode)}
            >
              <Text
                style={[
                  styles.toolbarButtonLabel,
                  viewMode === mode ? styles.toolbarButtonLabelActive : null,
                ]}
              >
                {mode}
              </Text>
            </Pressable>
          ))}
          <View style={styles.toolbarDivider} />
          <Pressable style={styles.commandChip} onPress={() => setComposer('/clear')}>
            <Text style={styles.commandChipLabel}>/clear</Text>
          </Pressable>
          <Pressable style={styles.commandChip} onPress={() => setComposer('/view log')}>
            <Text style={styles.commandChipLabel}>/view log</Text>
          </Pressable>
          <Pressable style={styles.commandChip} onPress={() => setComposer('/quit')}>
            <Text style={styles.commandChipLabel}>/quit</Text>
          </Pressable>
        </View>

        {error ? (
          <View style={styles.errorBanner}>
            <Text style={styles.errorBannerLabel}>Connection issue</Text>
            <Text style={styles.errorBannerText}>{error}</Text>
          </View>
        ) : null}

        <View style={[styles.workspace, isWide ? styles.workspaceWide : styles.workspaceStack]}>
          <View style={[styles.mainColumn, !isWide && viewMode === 'metrics' ? styles.mainColumnFull : null]}>
            {renderMainPane()}
          </View>
          {isWide && viewMode !== 'chat' ? renderSidePane() : null}
        </View>

        {!isWide && state ? <View style={styles.mobileMetrics}>{renderSidePane()}</View> : null}

        <View style={styles.composerShell}>
          <Text style={styles.composerLabel}>Command / prompt</Text>
          <View style={styles.composerRow}>
            <TextInput
              style={styles.composerInput}
              placeholder="Ask the NPU model, or use /view log, /clear, /quit"
              placeholderTextColor="#6f8597"
              selectionColor="#49dcb1"
              value={composer}
              onChangeText={setComposer}
              onSubmitEditing={() => void submitComposer()}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <Pressable style={styles.sendButton} onPress={() => void submitComposer()} disabled={submitting}>
              <Text style={styles.sendButtonLabel}>{submitting ? 'Sending…' : 'Send'}</Text>
            </Pressable>
          </View>
          <Text style={styles.helpText}>
            Slash commands still work here. View switching is local; chat clear and session stop remain server-side.
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

function SectionTitle({
  label,
  eyebrow,
  compact = false,
}: {
  label: string;
  eyebrow: string;
  compact?: boolean;
}) {
  return (
    <View style={compact ? styles.sectionTitleCompact : styles.sectionTitle}>
      <Text style={styles.sectionEyebrow}>{eyebrow}</Text>
      <Text style={styles.sectionLabel}>{label}</Text>
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#071018',
  },
  appShell: {
    flex: 1,
    backgroundColor: '#0b141b',
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 18,
    gap: 14,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
  },
  headerCopy: {
    flex: 1,
    gap: 6,
  },
  overline: {
    color: '#7cbca7',
    fontSize: 12,
    letterSpacing: 2,
    textTransform: 'uppercase',
    fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif" as never,
  },
  title: {
    color: '#f0f5f8',
    fontSize: 30,
    lineHeight: 34,
    fontWeight: '700',
    fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif" as never,
  },
  statusChip: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  statusReady: {
    backgroundColor: '#123d31',
  },
  statusStarting: {
    backgroundColor: '#423114',
  },
  statusFailed: {
    backgroundColor: '#4b1f21',
  },
  statusIdle: {
    backgroundColor: '#243341',
  },
  statusChipLabel: {
    color: '#f0f5f8',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 10,
  },
  toolbarButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: '#12222d',
    borderWidth: 1,
    borderColor: '#1e3442',
  },
  toolbarButtonActive: {
    backgroundColor: '#49dcb1',
    borderColor: '#49dcb1',
  },
  toolbarButtonLabel: {
    color: '#8fb0c5',
    textTransform: 'uppercase',
    fontSize: 12,
    fontWeight: '700',
  },
  toolbarButtonLabelActive: {
    color: '#08281e',
  },
  toolbarDivider: {
    width: 1,
    height: 22,
    backgroundColor: '#1f3340',
    marginHorizontal: 4,
  },
  commandChip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: '#161e2a',
  },
  commandChipLabel: {
    color: '#f4c278',
    fontSize: 12,
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', monospace" as never,
  },
  errorBanner: {
    borderRadius: 20,
    backgroundColor: '#351b1f',
    borderWidth: 1,
    borderColor: '#5d2930',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 4,
  },
  errorBannerLabel: {
    color: '#ff9d9d',
    fontWeight: '700',
  },
  errorBannerText: {
    color: '#f6d7d7',
  },
  workspace: {
    flex: 1,
    gap: 16,
  },
  workspaceWide: {
    flexDirection: 'row',
  },
  workspaceStack: {
    flexDirection: 'column',
  },
  mainColumn: {
    flex: 2,
  },
  mainColumnFull: {
    flex: 1,
  },
  sideColumn: {
    flex: 1,
    gap: 14,
  },
  mobileMetrics: {
    maxHeight: 280,
  },
  panelSurface: {
    flex: 1,
    backgroundColor: '#0f1821',
    borderRadius: 28,
    borderWidth: 1,
    borderColor: '#203341',
  },
  panelContent: {
    padding: 18,
    gap: 14,
  },
  loadingPanel: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  loadingTitle: {
    color: '#f0f5f8',
    fontSize: 24,
    fontWeight: '700',
  },
  loadingCopy: {
    color: '#8ca3b4',
    fontSize: 14,
  },
  panelHeaderRow: {
    paddingHorizontal: 18,
    paddingTop: 18,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  ghostButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: '#12222d',
  },
  ghostButtonLabel: {
    color: '#9fc2d8',
    fontSize: 12,
    fontWeight: '600',
  },
  modePill: {
    borderRadius: 999,
    backgroundColor: '#1a2b37',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  modePillLabel: {
    color: '#8cbfd6',
    textTransform: 'uppercase',
    fontSize: 11,
    letterSpacing: 1,
  },
  transcriptScroll: {
    flex: 1,
  },
  transcriptContent: {
    padding: 18,
    gap: 12,
  },
  emptyCopy: {
    color: '#7d95a7',
    fontSize: 15,
  },
  messageBubble: {
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 6,
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#15364a',
    maxWidth: '82%',
  },
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#131f29',
    borderWidth: 1,
    borderColor: '#223746',
    maxWidth: '88%',
  },
  messageRole: {
    color: '#7cbca7',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  messageText: {
    color: '#eef4f8',
    fontSize: 15,
    lineHeight: 22,
  },
  systemBanner: {
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#705123',
    backgroundColor: '#2d2212',
    padding: 14,
    gap: 6,
  },
  systemBannerLabel: {
    color: '#f4c278',
    fontSize: 12,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  systemBannerText: {
    color: '#f7e7c9',
    lineHeight: 20,
  },
  logScroll: {
    flex: 1,
  },
  logContent: {
    paddingHorizontal: 18,
    paddingBottom: 18,
    gap: 8,
  },
  logLine: {
    color: '#b4cad8',
    fontSize: 13,
    lineHeight: 19,
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', monospace" as never,
  },
  infoCard: {
    backgroundColor: '#0f1821',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: '#203341',
    padding: 16,
    gap: 12,
  },
  sectionTitle: {
    gap: 4,
  },
  sectionTitleCompact: {
    gap: 2,
  },
  sectionEyebrow: {
    color: '#6fae99',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 1.5,
  },
  sectionLabel: {
    color: '#f0f5f8',
    fontSize: 21,
    fontWeight: '700',
  },
  infoRow: {
    gap: 4,
  },
  infoLabel: {
    color: '#7b94a7',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  infoValue: {
    color: '#eef4f8',
    fontSize: 14,
    lineHeight: 20,
  },
  signalRow: {
    gap: 6,
  },
  signalLabel: {
    color: '#f0f5f8',
    fontSize: 14,
    fontWeight: '600',
  },
  signalMetric: {
    color: '#8da6b8',
    fontSize: 13,
  },
  signalSpark: {
    color: '#49dcb1',
    fontSize: 16,
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', monospace" as never,
  },
  noteLine: {
    color: '#b3c7d5',
    lineHeight: 20,
  },
  metricBlock: {
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#1f3340',
    padding: 14,
    gap: 10,
  },
  metricHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
    alignItems: 'center',
  },
  metricLabel: {
    color: '#eef4f8',
    fontSize: 15,
    fontWeight: '700',
  },
  metricValue: {
    color: '#94cdb9',
    fontSize: 13,
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', monospace" as never,
  },
  sparkline: {
    color: '#49dcb1',
    fontSize: 16,
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', monospace" as never,
  },
  artifactRow: {
    borderBottomWidth: 1,
    borderBottomColor: '#1b2b36',
    paddingBottom: 10,
    gap: 4,
  },
  artifactLabel: {
    color: '#7f95a7',
    fontSize: 12,
    textTransform: 'uppercase',
  },
  artifactValue: {
    color: '#e8eef3',
    fontSize: 14,
  },
  composerShell: {
    gap: 8,
  },
  composerLabel: {
    color: '#7cae99',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 1.4,
  },
  composerRow: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
  },
  composerInput: {
    flex: 1,
    minHeight: 56,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#234050',
    backgroundColor: '#101c26',
    color: '#eef4f8',
    paddingHorizontal: 18,
    paddingVertical: 14,
    fontSize: 15,
  },
  sendButton: {
    minWidth: 120,
    minHeight: 56,
    borderRadius: 20,
    backgroundColor: '#49dcb1',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  sendButtonLabel: {
    color: '#07231b',
    fontSize: 15,
    fontWeight: '800',
  },
  helpText: {
    color: '#7f96a8',
    fontSize: 13,
  },
});
