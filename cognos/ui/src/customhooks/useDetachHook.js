const useDetachHook = (setMemboxData, setLmdData, handleDetachMemoryToggle, selectedValue, apiEndpoint) => {
  const handleDetach = async (item) => {
    const { label } = selectedValue;
    const detachMem = { host: label, lmd: item };

    handleDetachMemoryToggle();

    try {
      const response = await fetch(`${apiEndpoint}/detach_lmd`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(detachMem)
      });

      if (response.ok) {
        const data = await response.json();
        setLmdData(data);
      }
    } catch (error) {}

    try {
      const response = await fetch(`${apiEndpoint}/lmds`, {
        mode: 'cors',
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        const boxdata = await response.json();
        setMemboxData(boxdata);
      }
    } catch (error) {}

  };

  return { handleDetach };
};

export default useDetachHook;