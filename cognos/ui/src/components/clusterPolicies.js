// clusterPolicies.js
const clusterPolicies = {
    // Round robin policy: assigns every two hosts to the same cluster, then cycles
    roundRobin: (hosts, clusterList, options = {}) => {
      const hostsPerCluster = options.minHostsPerCluster || 2;
      return hosts.map((host, index) => {
        const clusterIndex =
          Math.floor(index / hostsPerCluster) % clusterList.length;
        const cluster = clusterList[clusterIndex];
        return { ...host, cluster };
      });
    },
    // Round robin policy specifically for label-value pairs
    labelValueRoundRobin: (labelValuePairs, clusterList, options = {}) => {
      const pairsPerCluster = options.minHostsPerCluster || 2;
      return labelValuePairs.map((pair, index) => {
        const clusterIndex =
          Math.floor(index / pairsPerCluster) % clusterList.length;
        const cluster = clusterList[clusterIndex];
        return { ...pair, cluster };
      });
    },
  };
  
  // Export the policies object
  module.exports = clusterPolicies;
  