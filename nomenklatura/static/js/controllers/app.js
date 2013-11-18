function AppCtrl($scope, $window, $routeParams, $location, session) {
    $scope.session = {logged_in: false};

    session.get(function(data) {
        $scope.session = data;
    });
}

AppCtrl.$inject = ['$scope', '$window', '$routeParams', '$location', 'session'];