function ReviewCtrl($scope, $routeParams, $location, $timeout, $http, session) {
    $scope.dataset = {};
    $scope.entity = {};
    $scope.matches = {};
    $scope.filter = '';
    $scope.canonical = null;

    $http.get('/api/2/datasets/' + $routeParams.dataset).then(function(res) {
        $scope.dataset = res.data;
    });

    $scope.random = $routeParams.what == 'random';

    $scope.loadMatches = function(url, params) {
        $http.get(url, {params: params}).then(function(res) {
            $scope.matches = res.data;
        });
    };

    var getMatchParams = function() {
        return {
            dataset: $routeParams.dataset,
            name: $scope.entity.name,
            exclude: $scope.entity.id,
            limit: 10
        };
    };

    var filterTimeout = null;
    
    $scope.updateFilter = function() {
        if (filterTimeout) { $timeout.cancel(filterTimeout); }

        filterTimeout = $timeout(function() {
            var fparams = getMatchParams();
            fparams.filter = $scope.filter;
            $scope.loadMatches('/api/2/match', fparams);
        }, 500);
    };

    $scope.loadEntity = function() {
        //$scope.matches = {};
        var randomUrl = '/api/2/review/' +  $routeParams.dataset,
            entityUrl = '/api/2/entities/' +  $routeParams.what,
            url = $scope.random ? randomUrl : entityUrl;
        $http.get(url).then(function(res) {
            $scope.entity = res.data;
            $scope.canonical = $scope.entity.canonical;
            $scope.entity.selection = 'ENTITY';
            if ($scope.entity.invalid) {
                $scope.entity.selection = 'INVALID';
            } else if ($scope.canonical) {
                $scope.entity.canonical = $scope.canonical.id;
                $scope.entity.selection = $scope.canonical.id;
            }
            $scope.loadMatches('/api/2/match', getMatchParams());
        });
    };

    $scope.$watch('selection', function(e) {
        console.log(e);
    });

    $scope.updateEntity = function() {
        $scope.entity.reviewed = true;
        
        if ($scope.entity.selection == 'INVALID') {
            $scope.entity.invalid = true;
            $scope.entity.canonical = null;
        } else if ($scope.entity.selection == 'ENTITY') {
            $scope.entity.invalid = false;
            $scope.entity.canonical = null;
        } else {
            $scope.entity.invalid = false;
            $scope.entity.canonical = parseInt($scope.entity.selection, 10);
        }
        $http.post('/api/2/entities/' + $scope.entity.id, $scope.entity).then(function(res) {
            //console.log(res);
            if ($scope.random) {
                $scope.loadEntity();
            } else {
                $location.path('/entities/' + res.data.id);
            }
            // TODO: figure out a nice flashing thingie!
        });
        console.log($scope.entity);
    };

    $scope.loadEntity();
}

ReviewCtrl.$inject = ['$scope', '$routeParams', '$location', '$timeout', '$http', 'session'];

