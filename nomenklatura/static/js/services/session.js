nomenklatura.factory('session', ['$http', function($http) {
    var _authz = {},
        dfd = $http.get('/api/2/sessions');

    var requestAuthz = function(dataset_name) {
        if (!(dataset_name in _authz)) {
            _authz[dataset_name] = $http({
                url: '/api/2/sessions/authz',
                method: 'GET',
                params: {dataset: dataset_name}});
        }
        return _authz[dataset_name];
    };

    return {
        get: dfd.success,
        authz: requestAuthz
    };
}]);
