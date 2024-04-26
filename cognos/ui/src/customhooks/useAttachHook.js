const useAttachHook = (setMemboxData, setLmdData, handleAttachMemoryToggle, selectedValue, apiEndpoint) => {
  const handleAttach = async (formData) => {
    handleAttachMemoryToggle();
    const { label } = selectedValue;
    const obj = { host: label };
    const attachMem = { ...formData, ...obj };

    console.log(attachMem);

    try {
      const response = await fetch(`${apiEndpoint}/attach_lmd`, {
        mode: 'cors',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(attachMem)
      });

      if (response.ok) {
        const data = await response.json();
        setLmdData(data);
      }
    } catch (error) {
      
    }


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
    } catch (error) {
      
    }

    try {
        const response = await fetch(`${apiEndpoint}/activate_device`, {
          mode: 'cors',
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(attachMem)
        });

        if (response.ok) {
          const data = await response.json();
          setMemboxData(data);
        }

    } catch (error) {

      }


  };

  return { handleAttach };
};

export default useAttachHook;