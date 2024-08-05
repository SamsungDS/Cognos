const useDetachHook = (setMemboxData, setLmdData, handleDetachMemoryToggle, selectedValue, apiEndpoint) => {
  const handleDetach = async (item) => {
    const { label } = selectedValue;
    const detachMem = { host_name: label, dev_name: item };
    handleDetachMemoryToggle();

    try {
      const response = await fetch(`${apiEndpoint}/detach_device`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 
          'Content-Type': 'application/json',
          'accept': 'application/json',
          'Access-Control-Allow-Origin':'*'
        },
        body: JSON.stringify(detachMem)
      });

      if (response.ok) {
        const data = await response.json();
        setLmdData(data);
      }
    } catch (error) {}

    try {
      const response = await fetch(`${apiEndpoint}/devices`, {
        mode: 'cors',
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'accept': 'application/json',
          'Access-Control-Allow-Origin':'*'
        },
        body: JSON.stringify({
          "input": "cluster_id=CLUST1;command=ListDevices;FM_id=203;FM_endpoint=samsung.com"
        })
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