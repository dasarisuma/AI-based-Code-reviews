import React, { useState } from 'react';
import { Github, Code, Shield, Bug, FileText, Zap, Clock, User, GitBranch, AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import './types';
import { PRReviewRequest, PRReviewResponse, AgentName, AgentConfig, StatusType, ReviewComment } from './types';
import './App.css';

const App: React.FC = () => {
  const [prUrl, setPrUrl] = useState<string>('');
  const [githubToken, setGithubToken] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [reviewResult, setReviewResult] = useState<PRReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (): Promise<void> => {
    if (!prUrl.trim()) {
      setError('Please enter a valid PR URL');
      return;
    }

    setIsLoading(true);
    setError(null);
    setReviewResult(null);

    try {
      console.log('Sending request with:', { pr_url: prUrl, github_token: githubToken ? 'PROVIDED' : 'MISSING' });
      
      const requestBody: PRReviewRequest = {
        pr_url: prUrl,
        github_token: githubToken
      };

      const response = await fetch('http://localhost:8000/review-pr', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
      });

      console.log('Response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.log('Error response:', errorText);
        
        try {
          const errorData = JSON.parse(errorText);
          throw new Error(errorData.detail || `Server error: ${response.status}`);
        } catch (parseError) {
          throw new Error(`Server error (${response.status}): ${errorText}`);
        }
      }

      const result: PRReviewResponse = await response.json();
      console.log('Success response:', result);
      setReviewResult(result);
    } catch (err) {
      console.error('Full error:', err);
      setError(err instanceof Error ? err.message : 'An unexpected error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusColor = (status: string): string => {
    const statusLower = status.toLowerCase() as StatusType;
    switch (statusLower) {
      case 'approve':
        return 'text-green-600 bg-green-50 border-green-200';
      case 'needs changes':
        return 'text-orange-600 bg-orange-50 border-orange-200';
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const getStatusIcon = (status: string): React.ReactNode => {
    const statusLower = status.toLowerCase() as StatusType;
    switch (statusLower) {
      case 'approve':
        return <CheckCircle className="w-5 h-5" />;
      case 'needs changes':
        return <AlertCircle className="w-5 h-5" />;
      default:
        return <XCircle className="w-5 h-5" />;
    }
  };

  const agentConfigs: Record<AgentName, AgentConfig> = {
    CodeQuality: {
      icon: <Code className="w-6 h-6 text-blue-600" />,
      color: 'from-blue-400 to-cyan-500',
      border: 'border-blue-300'
    },
    BugDetection: {
      icon: <Bug className="w-6 h-6 text-red-600" />,
      color: 'from-red-400 to-pink-500',
      border: 'border-red-300'
    },
    Security: {
      icon: <Shield className="w-6 h-6 text-purple-600" />,
      color: 'from-purple-400 to-indigo-500',
      border: 'border-purple-300'
    },
    Dependency: {
      icon: <Zap className="w-6 h-6 text-yellow-600" />,
      color: 'from-yellow-400 to-orange-500',
      border: 'border-yellow-300'
    },
    Documentation: {
      icon: <FileText className="w-6 h-6 text-green-600" />,
      color: 'from-green-400 to-teal-500',
      border: 'border-green-300'
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-pink-100 via-purple-50 to-indigo-100">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-600 via-pink-600 to-blue-600 shadow-xl border-b-4 border-yellow-400">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="flex items-center space-x-4">
            <div className="bg-gradient-to-r from-yellow-400 to-orange-500 p-4 rounded-2xl shadow-lg transform rotate-3 hover:rotate-6 transition-transform">
              <Github className="w-10 h-10 text-white" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-white drop-shadow-lg">AutoPR</h1>
              <p className="text-purple-100 text-lg">🚀 AI-Powered Code Review System ✨</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Input Form */}
        <div className="bg-gradient-to-br from-white via-blue-50 to-purple-50 rounded-2xl shadow-2xl border-4 border-gradient-to-r from-pink-300 to-blue-300 p-8 mb-8 transform hover:scale-[1.02] transition-transform">
          <div className="flex items-center space-x-3 mb-6">
            <div className="bg-gradient-to-r from-green-400 to-blue-500 p-3 rounded-xl">
              <Code className="w-6 h-6 text-white" />
            </div>
            <h2 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">Review Pull Request 🎯</h2>
          </div>
          
          <div className="space-y-6">
            <div>
              <label className="block text-lg font-bold text-purple-700 mb-3 flex items-center space-x-2">
                <Github className="w-5 h-5 text-pink-500" />
                <span>🔗 GitHub Pull Request URL</span>
              </label>
              <input
                type="url"
                value={prUrl}
                onChange={(e) => setPrUrl(e.target.value)}
                placeholder="https://github.com/owner/repo/pull/123"
                className="w-full px-6 py-4 border-3 border-pink-300 rounded-xl focus:ring-4 focus:ring-purple-300 focus:border-purple-500 transition-all duration-300 bg-gradient-to-r from-pink-50 to-purple-50 text-gray-800 font-medium shadow-lg"
              />
            </div>

            <div>
              <label className="block text-lg font-bold text-purple-700 mb-3 flex items-center space-x-2">
                <Shield className="w-5 h-5 text-green-500" />
                <span>🔐 GitHub Personal Access Token</span>
              </label>
              
              <input
                type="password"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                className="w-full px-6 py-4 border-3 border-green-300 rounded-xl focus:ring-4 focus:ring-green-300 focus:border-green-500 transition-all duration-300 bg-gradient-to-r from-green-50 to-blue-50 text-gray-800 font-medium shadow-lg"
              />
              
              <p className="text-sm text-indigo-600 mt-3 bg-indigo-50 p-3 rounded-lg border-l-4 border-indigo-400">
                💡 <strong>Required for private repositories.</strong> Generate one at GitHub Settings → Developer settings → Personal access tokens
              </p>
            </div>

            <button
              onClick={handleSubmit}
              disabled={isLoading || !prUrl}
              className="w-full bg-gradient-to-r from-pink-500 via-purple-600 to-indigo-600 text-white py-4 px-8 rounded-2xl font-bold text-lg hover:from-pink-600 hover:via-purple-700 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center space-x-3 shadow-2xl transform hover:scale-105 active:scale-95"
            >
              {isLoading ? (
                <>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white"></div>
                  <span>🔍 Analyzing Magic in Progress...</span>
                </>
              ) : (
                <>
                  <Github className="w-6 h-6" />
                  <span>🚀 Start AI Review</span>
                  <Zap className="w-6 h-6 animate-pulse" />
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-gradient-to-r from-red-100 to-pink-100 border-3 border-red-400 rounded-2xl p-6 mb-8 shadow-xl">
            <div className="flex items-center">
              <XCircle className="w-8 h-8 text-red-600 mr-4 animate-bounce" />
              <div>
                <h3 className="text-lg font-bold text-red-800">🚨 Oops! Something went wrong</h3>
                <p className="text-red-700 font-medium">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Review Results */}
        {reviewResult && (
          <div className="space-y-6">
            {/* Summary Card */}
            <div className="bg-gradient-to-br from-white via-yellow-50 to-orange-50 rounded-2xl shadow-2xl border-4 border-yellow-300 p-8 transform hover:scale-[1.02] transition-transform">
              <div className="flex items-start justify-between mb-6">
                <div>
                  <h3 className="text-2xl font-bold bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent flex items-center space-x-2">
                    <span>📊 Review Summary</span>
                  </h3>
                  <p className="text-gray-700 text-lg mt-2 font-medium">{reviewResult.summary}</p>
                </div>
                <div className={`inline-flex items-center px-4 py-2 rounded-2xl text-lg font-bold border-2 shadow-lg ${getStatusColor(reviewResult.final_status)}`}>
                  {getStatusIcon(reviewResult.final_status)}
                  <span className="ml-2">{reviewResult.final_status}</span>
                </div>
              </div>

              {/* PR Info */}
              <div className="bg-gradient-to-r from-blue-100 via-purple-100 to-pink-100 rounded-xl p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 border-2 border-blue-200">
                <div className="flex items-center space-x-3 bg-white p-3 rounded-lg shadow-md">
                  <FileText className="w-6 h-6 text-blue-500" />
                  <div>
                    <p className="text-xs text-blue-600 font-bold">📄 TITLE</p>
                    <p className="text-sm font-bold truncate text-gray-800">{reviewResult.pr_info.title}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-3 bg-white p-3 rounded-lg shadow-md">
                  <User className="w-6 h-6 text-green-500" />
                  <div>
                    <p className="text-xs text-green-600 font-bold">👨‍💻 AUTHOR</p>
                    <p className="text-sm font-bold text-gray-800">{reviewResult.pr_info.author}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-3 bg-white p-3 rounded-lg shadow-md">
                  <GitBranch className="w-6 h-6 text-purple-500" />
                  <div>
                    <p className="text-xs text-purple-600 font-bold">🌿 BRANCH</p>
                    <p className="text-sm font-bold text-gray-800">{reviewResult.pr_info.branch}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-3 bg-white p-3 rounded-lg shadow-md">
                  <Clock className="w-6 h-6 text-orange-500" />
                  <div>
                    <p className="text-xs text-orange-600 font-bold">⚡ TIME</p>
                    <p className="text-sm font-bold text-gray-800">{reviewResult.execution_time.toFixed(2)}s</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Unified Comments */}
            <div className="bg-white rounded-2xl shadow-2xl border-4 border-purple-200 p-8">
              <h3 className="text-2xl font-bold mb-6 bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent flex items-center space-x-2">
                <span>🗒️ Review Comments</span>
                <span className="ml-2 text-sm font-normal bg-purple-100 text-purple-700 px-3 py-1 rounded-full border border-purple-300">
                  {reviewResult.comments.length} total
                </span>
              </h3>
              {reviewResult.comments.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-green-600 bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl border-2 border-green-200">
                  <CheckCircle className="w-16 h-16 mb-4 animate-pulse" />
                  <span className="text-2xl font-bold">🎉 No Issues Found</span>
                  <p className="text-green-500 mt-2">This PR looks great!</p>
                </div>
              ) : (
                <UnifiedComments comments={reviewResult.comments} />
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 border-t-4 border-yellow-400 mt-16">
        <div className="max-w-6xl mx-auto px-4 py-8 text-center">
          <div className="flex items-center justify-center space-x-3 mb-3">
            <div className="bg-yellow-400 p-2 rounded-lg">
              <Zap className="w-5 h-5 text-purple-600" />
            </div>
            <p className="text-white font-bold text-lg">AutoPR v1.0.0</p>
            <div className="bg-yellow-400 p-2 rounded-lg">
              <Code className="w-5 h-5 text-purple-600" />
            </div>
          </div>
          <p className="text-purple-100">🚀 Powered by AI for better code reviews ✨</p>
        </div>
      </footer>
    </div>
  );
};

export default App;

// Component to render aggregated per-line comments grouped by file
const severityColor: Record<string, string> = {
  critical: 'border-red-600 bg-red-50',
  high: 'border-red-400 bg-red-50',
  error: 'border-red-500 bg-red-50',
  warning: 'border-yellow-400 bg-yellow-50',
  medium: 'border-yellow-300 bg-yellow-50',
  info: 'border-blue-300 bg-blue-50',
  low: 'border-blue-200 bg-blue-50'
};

interface UnifiedProps { comments: ReviewComment[] }

const UnifiedComments: React.FC<UnifiedProps> = ({ comments }) => {
  // Group by file
  const byFile: Record<string, ReviewComment[]> = {};
  comments.forEach(c => {
    const key = c.file || 'unknown-file';
    (byFile[key] = byFile[key] || []).push(c);
  });
  const files = Object.keys(byFile).sort();

  return (
    <div className="space-y-10">
      {files.map(file => {
        const fileComments = byFile[file];
        return (
          <div key={file} className="border-2 border-purple-100 rounded-xl p-5 bg-gradient-to-br from-white to-purple-50 shadow-md">
            <h4 className="text-xl font-bold mb-4 flex items-center space-x-2">
              <span className="text-purple-700">📄 {file}</span>
              <span className="text-xs font-semibold bg-purple-100 text-purple-700 px-2 py-1 rounded-full border border-purple-300">{fileComments.length}</span>
            </h4>
            <div className="space-y-4">
              {fileComments.sort((a,b)=> (a.line||0)-(b.line||0)).map((c, idx) => {
                const sev = (c.severity || 'info').toLowerCase();
                const color = severityColor[sev] || severityColor['info'];
                return (
                  <div key={idx} className={`rounded-lg border-l-4 ${color} p-4 group transition-shadow hover:shadow-lg`}>
                    <div className="flex justify-between items-start gap-4">
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-sm font-semibold text-gray-800">Line {c.line}</p>
                          <span className="text-[10px] tracking-wide uppercase text-gray-500 font-medium">{c.source_agent}</span>
                        </div>
                        <p className="text-gray-900 text-sm leading-snug">{c.message}</p>
                        {c.suggestion && (
                          <div className="mt-2 text-xs text-gray-700 bg-white/70 px-3 py-2 rounded-lg border border-gray-200">
                            💡 <span className="font-semibold">Suggestion:</span> {c.suggestion}
                          </div>
                        )}
                      </div>
                      <span className={`text-xs font-bold h-fit px-2 py-1 rounded-md border ${color}`}>{sev}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};
