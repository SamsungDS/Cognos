export function DynamicField({ field, value, onChange }) {
    const { field_name, label, type, required, options } = field;

    const commonProps = {
        id: field_name,
        name: field_name,
        value: value ?? "",
        onChange: (e) => onChange(field_name, e.target.value),
        required,
    };

    return (
        <div className="field-group" >
            <label htmlFor={field_name} className="form-label-custom">
                {label} {required && <span className="required"></span>}
            </label>
            <input type={type} placeholder={`Enter ${label}`} {...commonProps} />
        </div>
    );
}