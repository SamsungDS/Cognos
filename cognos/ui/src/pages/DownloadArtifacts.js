import React, { useState } from 'react';
import { Download } from 'lucide-react';
import 'bootstrap/dist/css/bootstrap.min.css';
import './downloadArtifacts.css';

const DownloadArtifacts = () => {
  const [selectedArtifact, setSelectedArtifact] = useState('');
  const [downloading, setDownloading] = useState(false);

  return (
    <div className="page-container Content content_root about">
      {/* Row 1: Full Width Header */}
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

      {/* Row 2: Content with 1 Columns */}
      <div className="content-container">
        <div className="row">
          {/* Column 2: Download Section */}
          <div className="col-lg-12 col-md-12 mb-4">
            <div className="card card-dark rounded-3 h-100">
              <div className="card-body p-4">
                <h2 className="h5 mb-4">Download Artifact</h2>

                {/* Dropdown */}
                <div className="mb-4">
                  <label className="form-label text-slate small fw-medium">
                    Select Cognos Release
                  </label>
                  <select
                    value={selectedArtifact}
                    className="form-select form-select-dark"
                    disabled={downloading}
                  >
                    <option value="">-- Select an artifact --</option>
                  </select>
                </div>
                {/* Download Button */}
                <button
                  disabled={!selectedArtifact || downloading}
                  className="btn btn-download w-100 d-flex align-items-center justify-content-center"
                >
                  <Download className={`me-2 ${downloading ? 'animate-bounce' : ''}`} size={20} />
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