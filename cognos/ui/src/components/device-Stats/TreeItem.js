import React from 'react';
import PropTypes from 'prop-types';
import './deviceCard.css';
const TreeItem = ({ label, level = 0, hasChildren, isExpanded, toggleExpanded, onClick, isSelected, children }) => {
    const handleClick = (e) => {
        e.stopPropagation();
        if (hasChildren && toggleExpanded) {
            toggleExpanded(label);
        } else if (onClick) {
            onClick();
        }
    };

    return (
        <div style={{ marginLeft: `${level * 15}px` }}>
            <div className='tree-style'
                onClick={handleClick}
                style={{             
                    backgroundColor: isSelected ? '#195cc2ff' : 'transparent',
                    color: isSelected ? 'white' : '#ccc',  
                }}
                onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = '#2a2a2a';
                }}
                onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                }}
            >
                {hasChildren && (
                    <span style={{ marginRight: '5px', fontSize: '12px' }}>
                        {isExpanded ? '▼' : '▶'}
                    </span>
                )}
                <span style={{ fontSize: '16px' }} title={label}>{label}</span>
            </div>
            {hasChildren && isExpanded && <div>{children}</div>}
        </div>
    );
};
TreeItem.propTypes = {
    label: PropTypes.string.isRequired,
    level: PropTypes.number,
    hasChildren: PropTypes.bool,
    isExpanded: PropTypes.bool,
    onClick: PropTypes.func,
    isSelected: PropTypes.bool,
    toggleExpanded: PropTypes.func,
    children: PropTypes.node,
}
export default TreeItem;