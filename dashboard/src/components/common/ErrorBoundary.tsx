import { tr } from "../../i18n";
import { Component, type ReactNode, type ErrorInfo } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] gap-4 text-center">
          <div className="w-12 h-12 rounded-xl bg-loss/10 border border-loss/30 flex items-center justify-center">
            <AlertTriangle size={24} className="text-loss" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white mb-1">{tr("Page Error")}</h2>
            <p className="text-sm text-white/40 font-mono max-w-md">
              {tr(this.state.error?.message ?? 'An unexpected error occurred')}
            </p>
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-border text-sm text-white/60 hover:text-white hover:bg-white/10 transition-colors"
          >
            <RefreshCw size={14} />{tr("Retry")}</button>
        </div>
      );
    }
    return this.props.children;
  }
}
