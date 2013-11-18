nomenklatura.factory('session', ['$http', function($http) {
    var dfd = $http.get('/api/2/sessions');
    return {
        get: dfd.success
    };
}]);
