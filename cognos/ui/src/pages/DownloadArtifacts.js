import React, { useState, useEffect } from 'react';
import { Download, AlertCircle, CheckCircle, PackageX } from 'lucide-react';
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