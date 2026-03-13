import React, { useState, useEffect } from 'react';
import { Download, AlertCircle, CheckCircle, PackageX, Tag, Calendar, List, FileText } from 'lucide-react';
import 'bootstrap/dist/css/bootstrap.min.css';
import './downloadArtifacts.css';
import * as constants from '../../src/constant';

const DownloadArtifacts = () => {
  const apiEndpoint = constants.Configs.api_endpoint;
  const [artifacts, setArtifacts] = useState([]);
  const [selectedArtifact, setSelectedArtifact] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [loading, setLoading] = useState(true);

  // status: null | { type: 'success'|'error'|'unavailable', message: string }
  const [status, setStatus] = useState(null);

  // Fetch artifact list
  useEffect(() => {
    const fetchArtifacts = async () => {
      try {
        const res = await fetch(`${apiEndpoint}/list_artifact`, {
          mode: 'cors',
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'Access-Control-Allow-Origin': '*'
          },
        });
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        const data = await res.json();
        setArtifacts(data.artifacts);
      } catch (err) {
        setStatus({ type: 'error', message: `Failed to load artifacts: ${err.message}` });
      } finally {
        setLoading(false);
      }
    };

    fetchArtifacts();
  }, []);

  // Download handler
  const handleDownload = async () => {
    if (!selectedArtifact) return;

    const artifact = artifacts.find(a => a.id === parseInt(selectedArtifact));
    if (!artifact) return;

    // Guard: file not available on server
    // istanbul ignore next
    if (!artifact.available) {
      setStatus({
        type: 'unavailable',
        message: `"${artifact.name}" is registered but missing on the server.`,
      });
      return;
    }

    setDownloading(true);
    setStatus(null);

    try {
      const res = await fetch(
        `${apiEndpoint}/artifact/${artifact.id}/download_artifact`,
        { headers: { Accept: 'application/gzip' } }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(err.error || `${res.status}`);
      }

      // Trigger browser download
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = artifact.name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);

      setStatus({ type: 'success', message: `"${artifact.name}" downloaded successfully.` });
    } catch (err) {
      setStatus({ type: 'error', message: `Download failed: ${err.message}` });
    } finally {
      setDownloading(false);
    }
  };

  // Derived state
  const selectedObj = artifacts.find(a => a.id === parseInt(selectedArtifact));
  const isUnavailable = selectedObj && !selectedObj.available;
  const details = selectedObj;

  // Render
  return (
    <div className="page-container Content content_root about">

      {/* Row 1: Header */}
      <div className="row full-width-header mb-4">
        <div className="col-12">
          <div className="card card-dark rounded-3">
            <div className="card-body p-4">
              <div className="d-flex align-items-center mb-3">
                <h1 className="mb-0">Download Cognos Artifacts</h1>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Download Section */}
      <div className="content-container">
        <div className="row">
          <div className="col-lg-12 col-md-12 mb-4">
            <div className="card card-dark rounded-3 h-100">
              <div className="card-body p-4">
                <h2 className="h5 mb-4">Download Artifact</h2>

                {/* Dropdown */}
                <div className="mb-4">
                  <label className="form-label text-slate small fw-medium">
                    Select Cognos Release
                  </label>

                  {loading ? (
                    <div className="text-muted small">Loading artifacts...</div>
                  ) : (
                    <select
                      value={selectedArtifact}
                      onChange={e => { setSelectedArtifact(e.target.value); setStatus(null); }}
                      className="form-select form-select-dark"
                      disabled={downloading}
                    >
                      <option value="">-- Select an artifact --</option>
                      {artifacts.map(artifact => (
                        <option key={artifact.id} value={artifact.id}>
                          {artifact.name}
                          {!artifact.available ? ' ⚠ Unavailable' : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {/* Artifact Details Panel */}
                {selectedObj && details && (
                  <div
                    className="artifact-details-panel mb-4 rounded-3 p-3"
                  >
                    <div className="d-flex align-items-center mb-3">
                      <FileText size={15} className="me-2 text-info flex-shrink-0" />
                      <span className="small fw-semibold text-info" style={{ letterSpacing: '0.04em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
                        Release Information
                      </span>
                    </div>

                    <div className="row g-3">
                      {/* Release Name */}
                      {details.release_name && (
                        <div className="col-sm-6">
                          <div className="d-flex align-items-start gap-2">
                            <Tag size={14} className="flex-shrink-0 text-muted" />
                            <div>
                              <div className="text-muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Release Name</div>
                              <div className="small fw-medium">{details.release_name}</div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Release Notes */}
                      {details.release_notes && (
                        <div className="col-sm-6">
                          <div className="d-flex align-items-start gap-2">
                            <FileText size={14} className="flex-shrink-0 text-muted" />
                            <div className="w-100">
                              <div className="text-muted mb-1" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Release Notes</div>
                              <div className="small" style={{ lineHeight: '1.6', opacity: 0.85 }}>{details.release_notes}</div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Release Date */}
                      {details.release_date && (
                        <div className="col-sm-6">
                          <div className="d-flex align-items-start gap-2">
                            <Calendar size={14} className="flex-shrink-0 text-muted" />
                            <div>
                              <div className="text-muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Release Date</div>
                              <div className="small fw-medium">
                                {new Date(details.release_date).toLocaleDateString('en-US', {
                                  year: 'numeric', month: 'long', day: 'numeric'
                                })}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                      {/* Feature List */}
                      {details.feature_list && details.feature_list.length > 0 && (
                        <div className="col-sm-6">
                          <div className="d-flex align-items-start gap-2">
                            <List size={14} className="flex-shrink-0 text-muted" />
                            <div className="w-100">
                              <div className="text-muted mb-2" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                Features ({details.feature_list.length})
                              </div>
                              <ul className="list-unstyled mb-0" style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                                {details.feature_list.map((feature, idx) => (
                                  <li key={idx} className="d-flex align-items-start gap-2 small" style={{ opacity: 0.85 }}>
                                    <span
                                      className='feature-span-style'
                                    />
                                    {feature}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Availability warning */}
                {isUnavailable && (
                  <div className="alert alert-warning d-flex align-items-center mb-3 py-2">
                    <PackageX size={16} className="me-2 flex-shrink-0" />
                    <span className="small">
                      This file is not available on the server yet.
                    </span>
                  </div>
                )}

                {/* Status message */}
                {status && (
                  <div
                    className={`alert d-flex align-items-center mb-3 py-2 ${status.type === 'success'
                      ? 'alert-success'
                      : 'alert-danger'
                      }`}
                  >
                    {status.type === 'success'
                      ? <CheckCircle size={16} className="me-2 flex-shrink-0" />
                      : <AlertCircle size={16} className="me-2 flex-shrink-0" />
                    }
                    <span className="small">{status.message}</span>
                  </div>
                )}

                {/* Download Button */}
                <button
                  onClick={handleDownload}
                  disabled={!selectedArtifact || downloading || loading || isUnavailable}
                  className="btn btn-download w-100 d-flex align-items-center justify-content-center"
                >
                  <Download
                    className={`me-2 ${downloading ? 'animate-bounce' : ''}`}
                    size={20}
                  />
                  {downloading ? 'Downloading...' : 'Download Artifact'}
                </button>

              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DownloadArtifacts;