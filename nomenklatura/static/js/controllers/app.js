function AppCtrl($scope, $window, $routeParams, $location, $modal, session) {
    $scope.session = {logged_in: false};

    session.get(function(data) {
        $scope.session = data;
    });

    $scope.keyDownNotify = function($event) {
        //console.log($event);
        if(angular.lowercase($event.target.tagName) == 'body') {
            $scope.$broadcast('key-pressed', $event.keyCode);
            //$event.preventDefault();
        }
    };

    $scope.showProfile = function() {
        var d = $modal.open({
            templateUrl: '/static/templates/profile.html',
            controller: 'ProfileCtrl'
        });
    };
}

AppCtrl.$inject = ['$scope', '$window', '$routeParams', '$location', '$modal', 'session'];