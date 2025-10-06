import React from 'react';
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
            <div
                onClick={handleClick}
                style={{
                    padding: '6px 8px',
                    cursor: 'pointer',
                    backgroundColor: isSelected ? '#195cc2ff' : 'transparent',
                    borderRadius: '4px',
                    color: isSelected ? 'white' : '#ccc',
                    display: 'flex',
                    alignItems: 'center',
                    marginBottom: '2px'
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
                <span style={{ fontSize: '14px' }}>{label}</span>
            </div>
            {hasChildren && isExpanded && <div>{children}</div>}
        </div>
    );
};
export default TreeItem;