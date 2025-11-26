import React, { useState } from 'react';
import PropTypes from 'prop-types';
import './YAxisConfigModal.css';

const YAxisConfigModal = ({ isOpen, onClose, onSave, currentMin, currentMax }) => {
    const [minValue, setMinValue] = useState(currentMin?.toString() || '0');
    const [maxValue, setMaxValue] = useState(currentMax?.toString() || '100');
    const [error, setError] = useState('');

    const handleSave = () => {
        const min = parseFloat(minValue);
        const max = parseFloat(maxValue);

        if (isNaN(min) || isNaN(max)) {
            setError('Please enter valid numbers');
            return;
        }

        if (min >= max) {
            setError('Minimum value must be less than maximum value');
            return;
        }

        if (min < 0 || max < 0) {
            setError('Values cannot be negative');
            return;
        }

        setError('');
        onSave({ min, max });
        onClose();
    };

    const handleReset = () => {
        setMinValue('0');
        setMaxValue('100');
        setError('');
        onSave({ min: null, max: null });
        onClose();
    };

    const handleClose = () => {
        setError('');
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="modal-overlay">
            <div className="modal-container">
                <h3 className="modal-title">Configure Y-Axis Range</h3>

                <div className="form-group">
                    <label className="form-label" htmlFor='minValue'>Minimum Value</label>
                    <input
                        type="number"
                        value={minValue}
                        onChange={(e) => setMinValue(e.target.value)}
                        className="form-input"
                        placeholder="Enter minimum value"
                        aria-label="Minimum value"
                    />
                </div>

                <div className="form-group">
                    <label className="form-label" htmlFor='maxValue'>Maximum Value</label>
                    <input
                        type="number"
                        value={maxValue}
                        onChange={(e) => setMaxValue(e.target.value)}
                        className="form-input"
                        placeholder="Enter maximum value"
                        aria-label="Maximum value"
                    />
                </div>

                {error && (
                    <div className="error-message" role="alert">
                        {error}
                    </div>
                )}

                <div className="button-group">
                    <button
                        onClick={handleReset}
                        className="btn btn-reset"
                        aria-label="Reset to default values"
                    >
                        Reset to Default
                    </button>
                    <button
                        onClick={handleClose}
                        className="btn btn-cancel"
                        aria-label="Cancel"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        className="btn btn-primary"
                        aria-label="Apply changes"
                    >
                        Apply
                    </button>
                </div>
            </div>
        </div>
    );
};

YAxisConfigModal.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onSave: PropTypes.func.isRequired,
    currentMin: PropTypes.number,
    currentMax: PropTypes.number
};

YAxisConfigModal.defaultProps = {
    currentMin: 0,
    currentMax: 100
};

export default YAxisConfigModal;